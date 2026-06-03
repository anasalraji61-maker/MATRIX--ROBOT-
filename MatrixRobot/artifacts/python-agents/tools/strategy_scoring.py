"""
Passive Strategy Scoring Layer — Matrix V1.5

Tracks win/loss rates per strategy without ML.
Data accumulates with every trade decision and outcome.
"""
from __future__ import annotations

import json
import re
import os
from datetime import datetime, timezone
from typing import Any

_KNOWN_STRATEGIES = [
    "ICT",
    "Wyckoff",
    "Elliott",
    "Harmonic",
    "MTF",
    "Momentum",
    "Mean Reversion",
    "Volume Profile",
    "Chart Pattern",
]

_KEYWORD_MAP: dict[str, str] = {
    "ict": "ICT",
    "smc": "ICT",
    "choch": "ICT",
    "bos": "ICT",
    "order block": "ICT",
    "fvg": "ICT",
    "fair value gap": "ICT",
    "liquidity": "ICT",
    "killzone": "ICT",
    "wyckoff": "Wyckoff",
    "markup": "Wyckoff",
    "markdown": "Wyckoff",
    "accumulation": "Wyckoff",
    "distribution": "Wyckoff",
    "elliott": "Elliott",
    "wave": "Elliott",
    "harmonic": "Harmonic",
    "gartley": "Harmonic",
    "butterfly": "Harmonic",
    "bat pattern": "Harmonic",
    "crab pattern": "Harmonic",
    "mtf": "MTF",
    "multi.timeframe": "MTF",
    "h1": "MTF",
    "h4": "MTF",
    "d1": "MTF",
    "momentum": "Momentum",
    "rsi": "Momentum",
    "macd": "Momentum",
    "stoch": "Momentum",
    "mean reversion": "Mean Reversion",
    "mean-reversion": "Mean Reversion",
    "bb": "Mean Reversion",
    "bollinger": "Mean Reversion",
    "volume profile": "Volume Profile",
    "vwap": "Volume Profile",
    "poc": "Volume Profile",
    "chart pattern": "Chart Pattern",
    "head and shoulder": "Chart Pattern",
    "double top": "Chart Pattern",
    "double bottom": "Chart Pattern",
    "triangle": "Chart Pattern",
    "flag": "Chart Pattern",
}


def extract_strategies(reasons: list[str]) -> list[str]:
    """Parse brain reason strings and return list of matched strategy names."""
    found: set[str] = set()
    combined = " ".join(reasons).lower()
    for keyword, strategy in _KEYWORD_MAP.items():
        if keyword in combined:
            found.add(strategy)
    return list(found) if found else ["ICT"]


def _get_pool():
    dsn = os.environ.get("DATABASE_URL")
    if not dsn:
        return None
    try:
        from psycopg_pool import ConnectionPool
        pool = ConnectionPool(
            conninfo=dsn, min_size=1, max_size=2,
            kwargs={"autocommit": True}, open=True, timeout=5,
        )
        with pool.connection() as conn:
            conn.execute("SELECT 1")
        return pool
    except Exception:
        return None


_pool = None
_pool_checked = False


def _pg():
    global _pool, _pool_checked
    if _pool is not None:
        return _pool
    if _pool_checked:
        return None
    _pool_checked = True
    _pool = _get_pool()
    return _pool


def log_signal(
    symbol: str,
    signal: str,
    confidence: float,
    strategies: list[str],
    regime: str | None = None,
) -> None:
    """Called after a brain decision — logs each strategy attribution."""
    pool = _pg()
    if pool is None:
        return
    ts = datetime.now(timezone.utc)
    for strat in strategies:
        try:
            with pool.connection() as conn:
                conn.execute(
                    """
                    INSERT INTO strategy_scores
                      (strategy, symbol, regime, signal, confidence, outcome, ts)
                    VALUES (%s, %s, %s, %s, %s, NULL, %s)
                    """,
                    (strat, symbol.upper(), regime, signal, confidence, ts),
                )
        except Exception:
            pass


def update_outcome(symbol: str, pnl: float | None) -> None:
    """Called when a trade closes — attributes result to recent open signals."""
    pool = _pg()
    if pool is None:
        return
    if pnl is None:
        return
    outcome = "win" if pnl > 0 else ("loss" if pnl < 0 else "breakeven")
    try:
        with pool.connection() as conn:
            conn.execute(
                """
                UPDATE strategy_scores
                SET outcome = %s, pnl = %s
                WHERE id IN (
                    SELECT id FROM strategy_scores
                    WHERE UPPER(symbol) = %s
                      AND outcome IS NULL
                    ORDER BY ts DESC
                    LIMIT 5
                )
                """,
                (outcome, pnl, symbol.upper()),
            )
    except Exception:
        pass


def get_scores(window: int = 50) -> dict:
    """Return per-strategy performance stats over last N completed trades."""
    pool = _pg()
    if pool is None:
        return {"scores": [], "dominant_strategy": None, "window_trades": window, "updated_at": datetime.now(timezone.utc).isoformat()}

    try:
        with pool.connection() as conn:
            cur = conn.execute(
                """
                SELECT
                    strategy,
                    COUNT(*) FILTER (WHERE outcome IS NOT NULL) AS completed,
                    COUNT(*) FILTER (WHERE outcome = 'win') AS wins,
                    COUNT(*) FILTER (WHERE outcome = 'loss') AS losses,
                    COUNT(*) AS signals,
                    ROUND(AVG(confidence)::numeric, 4) AS avg_confidence,
                    MAX(ts) AS last_signal
                FROM (
                    SELECT * FROM strategy_scores
                    ORDER BY ts DESC
                    LIMIT %s
                ) sub
                GROUP BY strategy
                ORDER BY completed DESC, wins DESC
                """,
                (window * 3,),
            )
            rows = cur.fetchall()
    except Exception:
        return {"scores": [], "dominant_strategy": None, "window_trades": window, "updated_at": datetime.now(timezone.utc).isoformat()}

    scores = []
    for row in rows:
        strategy, completed, wins, losses, signals, avg_conf, last_sig = row
        win_rate = round(wins / completed, 4) if completed and completed > 0 else None
        scores.append({
            "strategy": strategy,
            "signals": int(signals),
            "completed": int(completed),
            "wins": int(wins),
            "losses": int(losses),
            "win_rate": float(win_rate) if win_rate is not None else None,
            "avg_confidence": float(avg_conf) if avg_conf else None,
            "last_signal": last_sig.isoformat() if last_sig else None,
        })

    dominant = None
    scored = [s for s in scores if s["win_rate"] is not None and s["completed"] >= 3]
    if scored:
        dominant = max(scored, key=lambda x: x["win_rate"])["strategy"]

    for s in scores:
        s["dominant"] = s["strategy"] == dominant

    return {
        "scores": scores,
        "dominant_strategy": dominant,
        "window_trades": window,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
