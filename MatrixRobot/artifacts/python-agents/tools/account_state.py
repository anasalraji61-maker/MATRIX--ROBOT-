"""Live account equity tracking with daily anchor + starting-balance lock.

Replaces the old hardcoded ACCOUNT_BALANCE=10_000 constant. Every cycle, we:
  1. Pull the real equity/balance from the MT5 bridge (`/account`).
  2. On first run, snapshot the starting balance (locked forever — prop firms
     evaluate drawdown vs the *initial* account size, not current equity).
  3. Anchor a "daily start equity" at broker/FundedNext server midnight to compute daily DD.
  4. Track which server-calendar dates had trading activity (for FundedNext's min-5-days
     rule).
  5. Maintain a high-water mark for trailing DD if a prop firm uses that model.

All persisted via the existing memory module (Redis if available, else
in-process dict). Safe to call multiple times per cycle — pure-ish.
"""
import logging
from datetime import datetime, timezone
from typing import Optional

from config import get_settings
from tools import memory, mt5_bridge
from tools.prop_time import today_key as _today_key
from tools import emergency_guard

logger = logging.getLogger("matrix.account_state")

_STARTING_BAL_KEY  = "prop_starting_balance"
_DAILY_START_KEY   = "prop_daily_start_equity"
_DAILY_DATE_KEY    = "prop_daily_date"
_TRADING_DAYS_KEY  = "prop_trading_days"
_HIGH_WATER_KEY    = "prop_high_water_equity"
_TRADES_TODAY_KEY  = "prop_trades_today"
_SMALL_TRADES_TODAY_KEY = "small_trades_today"
_QUALIFIED_TRADES_KEY = "prop_qualified_trades_count"


def _today_utc() -> str:
    """Broker server calendar day (FundedNext reset), not UTC."""
    return _today_key()


def _ns(key: str, account_id: str | None) -> str:
    """Namespace a memory key per account. account_id=None / 'primary'
    keeps the legacy un-suffixed key so existing single-account state
    persists unchanged."""
    if not account_id or account_id == "primary":
        return key
    return f"{key}__{account_id}"


async def refresh_account(
    account_id: str | None = None,
    bridge_url: str | None = None,
    starting_balance_override: float | None = None,
) -> dict:
    """Pull live account snapshot, update anchors, return enriched dict.

    Returns dict with: available, equity, balance, starting_balance,
    daily_start_equity, daily_drawdown_pct, total_drawdown_pct, profit_pct,
    high_water_equity, currency.
    """
    settings = get_settings()
    sk = lambda k: _ns(k, account_id)  # noqa: E731
    live = await mt5_bridge.get_live_account(bridge_url=bridge_url)
    if not live:
        # Bridge offline — return last cached anchors if we have them, so the
        # downstream agents can still reason about DD from memory.
        starting = memory.retrieve(sk(_STARTING_BAL_KEY)) or 0.0
        return {
            "available": False,
            "equity": 0.0,
            "balance": 0.0,
            "starting_balance": starting,
            "daily_start_equity": memory.retrieve(sk(_DAILY_START_KEY)) or starting,
            "high_water_equity": memory.retrieve(sk(_HIGH_WATER_KEY)) or starting,
            "daily_drawdown_pct": 0.0,
            "total_drawdown_pct": 0.0,
            "profit_pct": 0.0,
            "currency": "USD",
        }

    equity  = float(live.get("equity")  or live.get("balance") or 0.0)
    balance = float(live.get("balance") or 0.0)

    # ── Starting balance: per-account override > settings > first-run snapshot ─
    if starting_balance_override is not None and starting_balance_override > 0:
        starting = float(starting_balance_override)
        # Persist so other code paths (prop_rules) see the same anchor.
        memory.store(sk(_STARTING_BAL_KEY), starting, ttl_seconds=86400 * 365)
    else:
        starting = float(settings.prop_starting_balance or 0.0) if not account_id or account_id == "primary" else 0.0
        if starting <= 0:
            starting = memory.retrieve(sk(_STARTING_BAL_KEY)) or 0.0
            if not starting or starting <= 0:
                starting = equity or balance
                memory.store(sk(_STARTING_BAL_KEY), starting, ttl_seconds=86400 * 365)

    # ── Daily anchor: reset at broker server midnight ─────────────────
    today = _today_utc()
    if memory.retrieve(sk(_DAILY_DATE_KEY)) != today:
        memory.store(sk(_DAILY_DATE_KEY), today, ttl_seconds=86400 * 7)
        memory.store(sk(_DAILY_START_KEY), equity, ttl_seconds=86400 * 7)
        daily_start = equity
    else:
        daily_start = memory.retrieve(sk(_DAILY_START_KEY)) or equity

    # ── High-water mark ─────────────────────────────────────────────────
    hw = memory.retrieve(sk(_HIGH_WATER_KEY)) or equity
    if equity > hw:
        hw = equity
        memory.store(sk(_HIGH_WATER_KEY), hw, ttl_seconds=86400 * 365)

    daily_dd = max(0.0, (daily_start - equity) / max(starting, 1.0) * 100.0)
    total_dd = max(0.0, (starting     - equity) / max(starting, 1.0) * 100.0)
    profit_pct = (equity - starting) / max(starting, 1.0) * 100.0

    return {
        "available": True,
        "equity": round(equity, 2),
        "balance": round(balance, 2),
        "starting_balance": round(starting, 2),
        "daily_start_equity": round(daily_start, 2),
        "high_water_equity": round(hw, 2),
        "daily_drawdown_pct": round(daily_dd, 3),
        "total_drawdown_pct": round(total_dd, 3),
        "profit_pct": round(profit_pct, 3),
        "currency": live.get("currency", "USD"),
    }


def record_trading_day(account_id: str | None = None) -> int:
    """Mark today (UTC) as a trading day. Returns total trading-day count."""
    today = _today_utc()
    key = _ns(_TRADING_DAYS_KEY, account_id)
    days = list(memory.retrieve(key) or [])
    if today not in days:
        days.append(today)
        memory.store(key, days, ttl_seconds=86400 * 365)
    return len(days)


def trading_days_count(account_id: str | None = None) -> int:
    return len(memory.retrieve(_ns(_TRADING_DAYS_KEY, account_id)) or [])


def record_trade_opened(account_id: str | None = None) -> int:
    """Increment today's opened-trade counter. Returns new count for today.
    Called by execution_agent after every successful fill (paper or live).
    Counter resets automatically at broker/FundedNext server midnight.
    """
    today = _today_utc()
    key = _ns(_TRADES_TODAY_KEY, account_id)
    log = memory.retrieve(key) or {}
    if log.get("date") != today:
        log = {"date": today, "count": 0}
    log["count"] = int(log.get("count", 0)) + 1
    memory.store(key, log, ttl_seconds=86400 * 2)
    return log["count"]


def trades_today_count(account_id: str | None = None) -> int:
    """Trades opened today (UTC). Auto-resets at midnight."""
    today = _today_utc()
    log = memory.retrieve(_ns(_TRADES_TODAY_KEY, account_id)) or {}
    if log.get("date") != today:
        return 0
    return int(log.get("count", 0))


def record_small_trade_opened(account_id: str | None = None) -> int:
    today = _today_utc()
    key = _ns(_SMALL_TRADES_TODAY_KEY, account_id)
    log = memory.retrieve(key) or {}
    if log.get("date") != today:
        log = {"date": today, "count": 0}
    log["count"] = int(log.get("count", 0)) + 1
    memory.store(key, log, ttl_seconds=86400 * 2)
    return log["count"]


def small_trades_today_count(account_id: str | None = None) -> int:
    today = _today_utc()
    log = memory.retrieve(_ns(_SMALL_TRADES_TODAY_KEY, account_id)) or {}
    if log.get("date") != today:
        return 0
    return int(log.get("count", 0))


def count_small_open_positions(positions: list | None) -> int:
    return sum(1 for p in (positions or []) if str(p.get("trade_tier", "")).upper() == "SMALL")


def trading_days_list(account_id: str | None = None) -> list[str]:
    return list(memory.retrieve(_ns(_TRADING_DAYS_KEY, account_id)) or [])


def record_qualified_trade_close(account_id: str | None = None) -> int:
    """Increment closed-trade count for FundedNext min-trades rule."""
    key = _ns(_QUALIFIED_TRADES_KEY, account_id)
    count = int(memory.retrieve(key) or 0) + 1
    memory.store(key, count, ttl_seconds=86400 * 365)
    return count


def qualified_trades_count(account_id: str | None = None) -> int:
    return int(memory.retrieve(_ns(_QUALIFIED_TRADES_KEY, account_id)) or 0)


def check_min_hold(trade_id: str, positions: list, min_hold_seconds: int) -> Optional[dict]:
    """FAIL-CLOSED min-hold guard for FundedNext anti-scalping rule.

    Returns None if close is allowed. Returns an error dict (with success=False
    and explanatory message) if it must be blocked. Block reasons:
      - position not found in memory (cannot verify hold age)
      - opened_at missing on the position record
      - opened_at unparseable
      - age < min_hold_seconds
    """
    pos = next((p for p in (positions or []) if str(p.get("trade_id")) == str(trade_id)), None)
    if pos is None:
        return {
            "success": False,
            "blocked_by": "min_hold_guard",
            "message": (
                f"FN rule fail-closed: position {trade_id} not in memory, "
                f"cannot verify hold age >= {min_hold_seconds}s"
            ),
            "min_hold_seconds": min_hold_seconds,
        }
    opened_raw = pos.get("opened_at")
    if not opened_raw:
        return {
            "success": False, "blocked_by": "min_hold_guard",
            "message": f"FN rule fail-closed: position {trade_id} missing opened_at",
            "min_hold_seconds": min_hold_seconds,
        }
    try:
        opened = datetime.fromisoformat(str(opened_raw).replace("Z", "+00:00"))
        if opened.tzinfo is None:
            opened = opened.replace(tzinfo=timezone.utc)
    except Exception as e:
        return {
            "success": False, "blocked_by": "min_hold_guard",
            "message": (
                f"FN rule fail-closed: unparseable opened_at ({opened_raw!r}) "
                f"on position {trade_id}: {e}"
            ),
            "min_hold_seconds": min_hold_seconds,
        }
    age_s = (datetime.now(timezone.utc) - opened).total_seconds()
    if age_s < min_hold_seconds:
        return {
            "success": False, "blocked_by": "min_hold_guard",
            "message": (
                f"FN rule: position must be held >= {min_hold_seconds}s "
                f"(current age: {age_s:.1f}s). Wait "
                f"{min_hold_seconds - age_s:.1f}s more."
            ),
            "min_hold_seconds": min_hold_seconds,
            "current_age_seconds": round(age_s, 1),
        }
    return None


async def _log_external_close(
    position: dict,
    account_id: str | None,
    bridge_url: str | None,
) -> dict | None:
    """Record a position that disappeared from MT5 (TP/SL/manual/phone)."""
    from tools import close_logger

    try:
        return await close_logger.log_position_closed(
            position,
            account_id=account_id,
            bridge_url=bridge_url,
            source="external_reconcile",
        )
    except Exception:
        logger.exception("Failed to log reconciled close for %s", position.get("trade_id"))
        return None


async def reconcile_account(
    account_id: str | None = None,
    bridge_url: str | None = None,
) -> dict:
    """Reconcile memory open_positions with live MT5. Returns stats dict."""
    settings = get_settings()
    bridge_url = (bridge_url or settings.mt5_bridge_url or "").rstrip("/")
    pos_key = _ns("open_positions", account_id)
    label = account_id or "primary"

    mem = memory.retrieve(pos_key) or []
    result = {
        "account": label,
        "bridge_ok": False,
        "memory_count_before": len(mem),
        "live_count": 0,
        "ghost_removed": 0,
        "external_imported": 0,
        "positions": mem,
        "last_closed": None,
    }

    if not bridge_url:
        result["bridge_ok"] = True
        return result

    try:
        live = await mt5_bridge.get_live_positions(bridge_url=bridge_url)
        result["bridge_ok"] = True
    except Exception as e:
        logger.warning(f"reconcile_account bridge error ({label}): {e}")
        result["error"] = str(e)
        return result

    result["live_count"] = len(live or [])

    if not live:
        if mem:
            for p in mem:
                closed = await _log_external_close(p, account_id, bridge_url)
                if closed and not result["last_closed"]:
                    result["last_closed"] = closed
            result["ghost_removed"] = len(mem)
            logger.info(f"Cleared {len(mem)} ghost position(s) for {label}")
            memory.store(pos_key, [], ttl_seconds=86400 * 7)
        result["positions"] = []
        return result

    mem_by_id = {str(p.get("trade_id")): p for p in mem if p.get("trade_id")}
    synced: list[dict] = []
    live_ids: set[str] = set()

    for p in live:
        tid = str(p.get("ticket") or p.get("trade_id") or "")
        live_ids.add(tid)
        action = p.get("type") or p.get("action") or "BUY"
        prev = mem_by_id.get(tid, {})
        entry = {
            "trade_id": tid,
            "symbol": p.get("symbol", ""),
            "action": str(action).upper(),
            "lots": float(p.get("volume") or p.get("lots") or 0),
            "entry_price": float(p.get("open_price") or p.get("entry_price") or 0),
            "stop_loss": float(p.get("sl") or p.get("stop_loss") or 0),
            "take_profit": float(p.get("tp") or p.get("take_profit") or 0),
            "initial_stop_loss": float(
                prev.get("initial_stop_loss")
                or p.get("sl")
                or p.get("stop_loss")
                or 0
            ),
            "opened_at": p.get("open_time") or p.get("opened_at") or prev.get("opened_at"),
            "pnl": float(p.get("profit") or p.get("pnl") or 0),
            "trade_tier": prev.get("trade_tier"),
            "source": prev.get("source") or "matrix",
        }
        for key in (
            "strategy", "strategy_name", "strength", "spread_at_entry", "spread_pips",
            "council_approved", "council_meta_score", "scalp_strategy", "entry_reason",
            "skeptic_vote", "risk_vote", "mode",
        ):
            if prev.get(key) is not None:
                entry[key] = prev[key]
        if not prev:
            entry["source"] = "MT5_EXTERNAL"
            result["external_imported"] += 1
        synced.append(entry)

    for p in mem:
        tid = str(p.get("trade_id") or "")
        if tid and tid not in live_ids:
            closed = await _log_external_close(p, account_id, bridge_url)
            if closed:
                result["last_closed"] = closed
            result["ghost_removed"] += 1

    if result["ghost_removed"] or result["external_imported"] or len(synced) != len(mem):
        logger.info(
            f"Reconciled {label}: memory {len(mem)} -> live {len(synced)} "
            f"(ghosts={result['ghost_removed']}, external={result['external_imported']})"
        )
        memory.store(pos_key, synced, ttl_seconds=86400 * 7)

    result["positions"] = synced
    return result


async def sync_open_positions(
    account_id: str | None = None,
    bridge_url: str | None = None,
) -> list[dict]:
    """Backward-compatible wrapper — returns position list only."""
    result = await reconcile_account(account_id=account_id, bridge_url=bridge_url)
    return result.get("positions") or []


def reset_for_new_challenge() -> None:
    """Wipe anchors — call when starting a fresh prop-firm challenge."""
    from tools import accounts as accounts_mod

    base_keys = (
        _STARTING_BAL_KEY, _DAILY_START_KEY, _DAILY_DATE_KEY,
        _TRADING_DAYS_KEY, _HIGH_WATER_KEY, _TRADES_TODAY_KEY,
        _SMALL_TRADES_TODAY_KEY, _QUALIFIED_TRADES_KEY,
        "prop_daily_pnl_log", "open_positions",
    )
    account_ids: set[str] = {"primary"}
    try:
        account_ids.update(a.id for a in accounts_mod.enabled_accounts())
    except Exception:
        pass
    for k in getattr(memory, "_store", {}):
        if "__" in k:
            account_ids.add(k.rsplit("__", 1)[1])

    for acct_id in account_ids:
        for k in base_keys:
            memory.store(_ns(k, None if acct_id == "primary" else acct_id), None, ttl_seconds=1)

    emergency_guard.clear_lockout()
