"""Recent closed trades from Postgres — GET /agents/trades/outcomes"""
from __future__ import annotations

from fastapi import APIRouter, Query

from tools import memory

router = APIRouter()


@router.get("/trades/outcomes")
async def recent_trade_outcomes(
    symbol: str | None = None,
    limit: int = Query(default=20, ge=1, le=100),
):
    rows = memory.get_recent_outcomes(symbol=symbol or None, limit=limit)
    return {
        "count": len(rows),
        "outcomes": list(reversed(rows)),
    }
