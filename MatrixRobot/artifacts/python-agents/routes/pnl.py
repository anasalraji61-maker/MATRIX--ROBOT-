"""P&L Summary route — GET /agents/pnl/summary"""
from __future__ import annotations

import os
from datetime import datetime, timezone, timedelta
from fastapi import APIRouter

router = APIRouter()


def _pool():
    dsn = os.environ.get("DATABASE_URL")
    if not dsn:
        return None
    try:
        from psycopg_pool import ConnectionPool
        p = ConnectionPool(conninfo=dsn, min_size=1, max_size=2,
                           kwargs={"autocommit": True}, open=True, timeout=5)
        with p.connection() as c:
            c.execute("SELECT 1")
        return p
    except Exception:
        return None


_pg = None
_pg_checked = False


def _get_pg():
    global _pg, _pg_checked
    if _pg is not None:
        return _pg
    if _pg_checked:
        return None
    _pg_checked = True
    _pg = _pool()
    return _pg


@router.get("/pnl/summary")
async def pnl_summary():
    pool = _get_pg()
    now = datetime.now(timezone.utc)
    day_start = now.replace(hour=0, minute=0, second=0, microsecond=0)

    empty = {
        "today_realized": 0.0,
        "total_realized": 0.0,
        "today_trades": 0,
        "total_trades": 0,
        "total_wins": 0,
        "total_losses": 0,
        "win_rate": None,
        "best_trade": None,
        "worst_trade": None,
        "updated_at": now.isoformat(),
    }

    if pool is None:
        return empty

    try:
        with pool.connection() as conn:
            cur = conn.execute(
                """
                SELECT
                    COALESCE(SUM(pnl) FILTER (WHERE ts >= %s), 0)   AS today_realized,
                    COALESCE(SUM(pnl), 0)                            AS total_realized,
                    COUNT(*) FILTER (WHERE ts >= %s)                 AS today_trades,
                    COUNT(*)                                          AS total_trades,
                    COUNT(*) FILTER (WHERE pnl > 0)                  AS total_wins,
                    COUNT(*) FILTER (WHERE pnl < 0)                  AS total_losses,
                    MAX(pnl)                                          AS best_trade,
                    MIN(pnl)                                          AS worst_trade
                FROM trade_outcomes
                WHERE pnl IS NOT NULL
                """,
                (day_start, day_start),
            )
            row = cur.fetchone()
    except Exception:
        return empty

    if not row:
        return empty

    today_r, total_r, today_t, total_t, wins, losses, best, worst = row
    completed = int(wins or 0) + int(losses or 0)
    win_rate = round(float(wins) / completed, 4) if completed > 0 else None

    return {
        "today_realized": float(today_r or 0),
        "total_realized": float(total_r or 0),
        "today_trades": int(today_t or 0),
        "total_trades": int(total_t or 0),
        "total_wins": int(wins or 0),
        "total_losses": int(losses or 0),
        "win_rate": win_rate,
        "best_trade": float(best) if best is not None else None,
        "worst_trade": float(worst) if worst is not None else None,
        "updated_at": now.isoformat(),
    }
