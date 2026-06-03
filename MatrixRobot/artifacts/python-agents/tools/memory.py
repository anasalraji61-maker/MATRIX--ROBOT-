"""
Persistent memory layer for agent state.

Backends (in priority order):
  1. PostgreSQL (Replit Postgres) — durable across restarts. Used when
     DATABASE_URL is set. All history (decisions, outcomes, cycles, DD
     snapshots) goes into dedicated tables; ad-hoc keys go to kv_store.
  2. Redis — when REDIS_URL is set and Postgres isn't.
  3. In-memory dict — last-resort fallback (lost on restart).

Schema is created by the database skill; see tables: brain_decisions,
trade_outcomes, cycle_logs, drawdown_snapshots, kv_store.
"""
import json
import os
from datetime import datetime, timezone, timedelta
from typing import Any
from config import get_settings

_store: dict[str, str] = {}
_redis_client = None
_pg_pool = None
_pg_checked = False


def _get_pg_pool():
    """Lazy-init a Postgres connection pool. Returns None if unavailable."""
    global _pg_pool, _pg_checked
    if _pg_pool is not None:
        return _pg_pool
    if _pg_checked:
        return None
    _pg_checked = True
    dsn = os.environ.get("DATABASE_URL")
    if not dsn:
        return None
    try:
        from psycopg_pool import ConnectionPool
        _pg_pool = ConnectionPool(
            conninfo=dsn,
            min_size=1,
            max_size=4,
            kwargs={"autocommit": True},
            open=True,
            timeout=10,
        )
        # Sanity check
        with _pg_pool.connection() as conn:
            conn.execute("SELECT 1")
        return _pg_pool
    except Exception:
        _pg_pool = None
        return None


def has_postgres() -> bool:
    return _get_pg_pool() is not None


def _get_redis():
    global _redis_client
    settings = get_settings()
    if not settings.has_redis:
        return None
    if _redis_client is not None:
        return _redis_client
    try:
        import redis
        _redis_client = redis.from_url(settings.redis_url, decode_responses=True)
        _redis_client.ping()
        return _redis_client
    except Exception:
        return None


# ── Generic KV (used by store/retrieve/append_to_list) ─────────────

def store(key: str, value: Any, ttl_seconds: int = 3600) -> None:
    serialized = json.dumps(value, default=str)
    pool = _get_pg_pool()
    if pool is not None:
        try:
            expires = None
            if ttl_seconds and ttl_seconds > 0:
                expires = datetime.now(timezone.utc) + timedelta(seconds=ttl_seconds)
            with pool.connection() as conn:
                conn.execute(
                    """
                    INSERT INTO kv_store (key, value, updated_at, expires_at)
                    VALUES (%s, %s::jsonb, NOW(), %s)
                    ON CONFLICT (key) DO UPDATE
                      SET value = EXCLUDED.value,
                          updated_at = NOW(),
                          expires_at = EXCLUDED.expires_at
                    """,
                    (key, serialized, expires),
                )
            return
        except Exception:
            pass
    client = _get_redis()
    if client:
        try:
            client.set(f"matrix:{key}", serialized, ex=ttl_seconds)
            return
        except Exception:
            pass
    _store[key] = serialized


def retrieve(key: str) -> Any | None:
    pool = _get_pg_pool()
    if pool is not None:
        try:
            with pool.connection() as conn:
                cur = conn.execute(
                    """
                    SELECT value FROM kv_store
                    WHERE key = %s
                      AND (expires_at IS NULL OR expires_at > NOW())
                    """,
                    (key,),
                )
                row = cur.fetchone()
                if row is None:
                    return None
                val = row[0]
                # psycopg returns jsonb already decoded
                return val
        except Exception:
            pass
    client = _get_redis()
    if client:
        try:
            raw = client.get(f"matrix:{key}")
            return json.loads(raw) if raw else None
        except Exception:
            pass
    raw = _store.get(key)
    return json.loads(raw) if raw else None


def append_to_list(key: str, item: Any, max_length: int = 100,
                   ttl_seconds: int = 3600) -> None:
    existing = retrieve(key) or []
    if not isinstance(existing, list):
        existing = []
    existing.append(item)
    if len(existing) > max_length:
        existing = existing[-max_length:]
    store(key, existing, ttl_seconds=ttl_seconds)


# Long-lived history TTL (30 days) — used for KV fallback paths.
_HISTORY_TTL = 86400 * 30


# ── Cycle results ──────────────────────────────────────────────────

def store_cycle_result(result: dict) -> None:
    """Persist a cycle result. Goes to cycle_logs table if PG, KV otherwise."""
    store("last_cycle", result, ttl_seconds=86400)

    pool = _get_pg_pool()
    if pool is not None:
        try:
            cycle_id = result.get("cycle_id") or result.get("id")
            started = result.get("started_at")
            finished = result.get("finished_at")
            status = result.get("status")
            mode = result.get("mode")
            symbols = result.get("symbols_analyzed")
            decision = result.get("decision")
            with pool.connection() as conn:
                conn.execute(
                    """
                    INSERT INTO cycle_logs
                      (cycle_id, started_at, finished_at, status, mode,
                       symbols_analyzed, decision, raw)
                    VALUES (%s, COALESCE(%s::timestamptz, NOW()), %s::timestamptz,
                            %s, %s, %s::jsonb, %s::jsonb, %s::jsonb)
                    ON CONFLICT (cycle_id) DO UPDATE
                      SET finished_at = EXCLUDED.finished_at,
                          status = EXCLUDED.status,
                          mode = EXCLUDED.mode,
                          symbols_analyzed = EXCLUDED.symbols_analyzed,
                          decision = EXCLUDED.decision,
                          raw = EXCLUDED.raw
                    """,
                    (
                        cycle_id,
                        started,
                        finished,
                        status,
                        mode,
                        json.dumps(symbols, default=str) if symbols is not None else None,
                        json.dumps(decision, default=str) if decision is not None else None,
                        json.dumps(result, default=str),
                    ),
                )
            return
        except Exception:
            pass
    append_to_list("cycle_history", result, max_length=50)


def get_last_cycle() -> dict | None:
    pool = _get_pg_pool()
    if pool is not None:
        try:
            with pool.connection() as conn:
                cur = conn.execute(
                    "SELECT raw FROM cycle_logs ORDER BY started_at DESC LIMIT 1"
                )
                row = cur.fetchone()
                if row and row[0]:
                    return row[0]
        except Exception:
            pass
    return retrieve("last_cycle")


# ── Agent state (live snapshot) ────────────────────────────────────

def store_state(state: dict) -> None:
    state["updated_at"] = datetime.now(timezone.utc).isoformat()
    store("agent_state", state, ttl_seconds=86400 * 7)


def get_state() -> dict | None:
    return retrieve("agent_state")


# ── Brain decisions ────────────────────────────────────────────────

def log_brain_decision(decision: dict) -> None:
    """Append a single brain analysis. Schema:
    {ts, symbol, signal, strength, reasons, llm_analysis, source}."""
    decision = dict(decision)
    decision.setdefault("ts", datetime.now(timezone.utc).isoformat())

    # Passive strategy scoring — fire and forget
    try:
        from tools.strategy_scoring import extract_strategies, log_signal
        signal = str(decision.get("signal", "HOLD")).upper()
        if signal in ("BUY", "SELL"):
            strats = extract_strategies(list(decision.get("reasons") or []))
            log_signal(
                symbol=str(decision.get("symbol", "UNKNOWN")),
                signal=signal,
                confidence=float(decision.get("strength") or 0.0),
                strategies=strats,
            )
    except Exception:
        pass

    pool = _get_pg_pool()
    if pool is not None:
        try:
            with pool.connection() as conn:
                conn.execute(
                    """
                    INSERT INTO brain_decisions
                      (ts, symbol, signal, strength, reasons, llm_analysis, source, raw)
                    VALUES (COALESCE(%s::timestamptz, NOW()), %s, %s, %s,
                            %s::jsonb, %s, %s, %s::jsonb)
                    """,
                    (
                        decision.get("ts"),
                        str(decision.get("symbol", "")).upper() or "UNKNOWN",
                        decision.get("signal"),
                        _to_float(decision.get("strength")),
                        json.dumps(decision.get("reasons"), default=str)
                            if decision.get("reasons") is not None else None,
                        decision.get("llm_analysis"),
                        decision.get("source"),
                        json.dumps(decision, default=str),
                    ),
                )
            return
        except Exception:
            pass
    append_to_list("brain_decisions", decision, max_length=200,
                   ttl_seconds=_HISTORY_TTL)


def get_recent_decisions(symbol: str | None = None, limit: int = 10) -> list[dict]:
    """Return the most recent brain decisions, optionally filtered by symbol."""
    pool = _get_pg_pool()
    if pool is not None:
        try:
            with pool.connection() as conn:
                if symbol:
                    cur = conn.execute(
                        """
                        SELECT raw FROM brain_decisions
                        WHERE UPPER(symbol) = %s
                        ORDER BY ts DESC LIMIT %s
                        """,
                        (symbol.upper(), int(limit)),
                    )
                else:
                    cur = conn.execute(
                        "SELECT raw FROM brain_decisions ORDER BY ts DESC LIMIT %s",
                        (int(limit),),
                    )
                rows = cur.fetchall()
            # Reverse to chronological order (oldest first) to match previous API.
            return [r[0] for r in reversed(rows) if r and r[0]]
        except Exception:
            pass
    history = retrieve("brain_decisions") or []
    if symbol:
        sym = symbol.upper()
        history = [d for d in history if str(d.get("symbol", "")).upper() == sym]
    return history[-limit:]


# ── Trade outcomes ─────────────────────────────────────────────────

def log_trade_outcome(outcome: dict) -> None:
    """Append a closed-trade outcome.
    Schema: {ts, ticket, symbol, side, entry, exit, volume, pnl, reason}."""
    outcome = dict(outcome)
    outcome.setdefault("ts", datetime.now(timezone.utc).isoformat())

    # Update strategy scores with outcome
    try:
        from tools.strategy_scoring import update_outcome
        update_outcome(
            symbol=str(outcome.get("symbol", "UNKNOWN")),
            pnl=_to_float(outcome.get("pnl")),
        )
    except Exception:
        pass

    pool = _get_pg_pool()
    if pool is not None:
        try:
            ticket = outcome.get("ticket")
            ticket_val = int(ticket) if ticket is not None else None
            with pool.connection() as conn:
                conn.execute(
                    """
                    INSERT INTO trade_outcomes
                      (ts, ticket, symbol, side, entry, exit, volume, pnl, reason, raw)
                    VALUES (COALESCE(%s::timestamptz, NOW()), %s, %s, %s,
                            %s, %s, %s, %s, %s, %s::jsonb)
                    ON CONFLICT (ticket) WHERE ticket IS NOT NULL
                      DO UPDATE SET exit = EXCLUDED.exit,
                                    pnl  = EXCLUDED.pnl,
                                    reason = EXCLUDED.reason,
                                    raw  = EXCLUDED.raw
                    """,
                    (
                        outcome.get("ts"),
                        ticket_val,
                        str(outcome.get("symbol", "")).upper() or "UNKNOWN",
                        outcome.get("side"),
                        _to_float(outcome.get("entry")),
                        _to_float(outcome.get("exit")),
                        _to_float(outcome.get("volume")),
                        _to_float(outcome.get("pnl")),
                        outcome.get("reason"),
                        json.dumps(outcome, default=str),
                    ),
                )
            return
        except Exception:
            pass
    append_to_list("trade_outcomes", outcome, max_length=200,
                   ttl_seconds=_HISTORY_TTL)


def get_recent_outcomes(symbol: str | None = None, limit: int = 10) -> list[dict]:
    pool = _get_pg_pool()
    if pool is not None:
        try:
            with pool.connection() as conn:
                if symbol:
                    cur = conn.execute(
                        """
                        SELECT raw FROM trade_outcomes
                        WHERE UPPER(symbol) = %s
                        ORDER BY ts DESC LIMIT %s
                        """,
                        (symbol.upper(), int(limit)),
                    )
                else:
                    cur = conn.execute(
                        "SELECT raw FROM trade_outcomes ORDER BY ts DESC LIMIT %s",
                        (int(limit),),
                    )
                rows = cur.fetchall()
            return [r[0] for r in reversed(rows) if r and r[0]]
        except Exception:
            pass
    outcomes = retrieve("trade_outcomes") or []
    if symbol:
        sym = symbol.upper()
        outcomes = [o for o in outcomes if str(o.get("symbol", "")).upper() == sym]
    return outcomes[-limit:]


# ── Drawdown snapshots (DD audit trail for FN compliance review) ───

def log_drawdown_snapshot(snap: dict) -> None:
    """Persist a drawdown / risk snapshot. Called by the cycle pipeline so
    FN compliance has a tamper-evident audit trail."""
    snap = dict(snap)
    snap.setdefault("ts", datetime.now(timezone.utc).isoformat())
    pool = _get_pg_pool()
    if pool is None:
        # Keep a rolling KV copy as fallback
        append_to_list("drawdown_snapshots", snap, max_length=500,
                       ttl_seconds=_HISTORY_TTL)
        return
    try:
        with pool.connection() as conn:
            conn.execute(
                """
                INSERT INTO drawdown_snapshots
                  (ts, balance, equity, daily_dd_pct, total_dd_pct,
                   open_positions, open_risk_pct, margin_used_pct, raw)
                VALUES (COALESCE(%s::timestamptz, NOW()), %s, %s, %s, %s,
                        %s, %s, %s, %s::jsonb)
                """,
                (
                    snap.get("ts"),
                    _to_float(snap.get("balance")),
                    _to_float(snap.get("equity")),
                    _to_float(snap.get("daily_dd_pct")),
                    _to_float(snap.get("total_dd_pct")),
                    _to_int(snap.get("open_positions")),
                    _to_float(snap.get("open_risk_pct")),
                    _to_float(snap.get("margin_used_pct")),
                    json.dumps(snap, default=str),
                ),
            )
    except Exception:
        append_to_list("drawdown_snapshots", snap, max_length=500,
                       ttl_seconds=_HISTORY_TTL)


def get_recent_drawdown_snapshots(limit: int = 100) -> list[dict]:
    pool = _get_pg_pool()
    if pool is not None:
        try:
            with pool.connection() as conn:
                cur = conn.execute(
                    "SELECT raw FROM drawdown_snapshots ORDER BY ts DESC LIMIT %s",
                    (int(limit),),
                )
                rows = cur.fetchall()
            return [r[0] for r in reversed(rows) if r and r[0]]
        except Exception:
            pass
    return (retrieve("drawdown_snapshots") or [])[-limit:]


# ── Health checks ──────────────────────────────────────────────────

def is_redis_connected() -> bool:
    client = _get_redis()
    if client is None:
        return False
    try:
        return client.ping()
    except Exception:
        return False


def is_postgres_connected() -> bool:
    pool = _get_pg_pool()
    if pool is None:
        return False
    try:
        with pool.connection() as conn:
            conn.execute("SELECT 1")
        return True
    except Exception:
        return False


# ── Helpers ────────────────────────────────────────────────────────

def _to_float(v: Any) -> float | None:
    if v is None or v == "":
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _to_int(v: Any) -> int | None:
    if v is None or v == "":
        return None
    try:
        return int(v)
    except (TypeError, ValueError):
        return None
