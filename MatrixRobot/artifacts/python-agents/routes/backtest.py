"""
Backtest routes — POST /agents/backtest/run, POST /agents/backtest/portfolio.

Deterministic strategy replay over historical Twelve Data bars. See
`backtest/engine.py` for the methodology and the look-ahead-free guarantees.
"""
from __future__ import annotations
import asyncio
import logging
from typing import Optional

from fastapi import APIRouter
from pydantic import BaseModel, Field

from backtest.engine import run_backtest

router = APIRouter()
logger = logging.getLogger("matrix.backtest.api")


class BacktestRequest(BaseModel):
    symbol: str = Field(..., examples=["EURUSD"])
    bars_limit: int = Field(2000, ge=300, le=5000,
                            description="Number of historical bars (H1: 2000≈83 days)")
    timeframe: str = Field("H1", examples=["H1", "M15", "H4", "D1"])
    include_trades: bool = Field(True, description="If false, returns stats only (faster JSON)")


class PortfolioRequest(BaseModel):
    symbols: list[str] = Field(..., min_length=1, max_length=10)
    bars_limit: int = Field(2000, ge=300, le=5000)
    timeframe: str = Field("H1")


@router.post("/backtest/run")
async def backtest_one(req: BacktestRequest) -> dict:
    """Run a deterministic backtest on a single symbol. Typical runtime:
    2000 H1 bars ≈ 5-15 seconds depending on instrument."""
    result = await run_backtest(req.symbol, bars_limit=req.bars_limit,
                                timeframe=req.timeframe)
    payload: dict = {
        "symbol": result.symbol,
        "timeframe": result.timeframe,
        "bars_count": result.bars_count,
        "warmup_bars": result.warmup_bars,
        "stats": result.stats,
    }
    if req.include_trades:
        payload["trades"] = result.trades
    else:
        payload["n_trades"] = len(result.trades)
    return payload


@router.post("/backtest/portfolio")
async def backtest_portfolio(req: PortfolioRequest) -> dict:
    """Run backtests across multiple symbols in parallel; aggregate stats."""
    async def _one(sym: str) -> tuple[str, dict]:
        try:
            r = await run_backtest(sym, bars_limit=req.bars_limit,
                                   timeframe=req.timeframe)
            return sym.upper(), {"stats": r.stats, "bars_count": r.bars_count,
                                  "n_trades": len(r.trades)}
        except Exception as e:
            logger.exception(f"backtest failed for {sym}")
            return sym.upper(), {"error": f"{type(e).__name__}: {e}"}

    results = await asyncio.gather(*[_one(s) for s in req.symbols])
    per_symbol = dict(results)

    # Aggregate using exact gross win/loss R from each per-symbol stats block
    # — equal-weight basket, every R counted at face value (TP, SL, TIMEOUT, EOD).
    total_trades = 0
    total_r = 0.0
    total_wins = 0
    gw = 0.0; gl = 0.0
    for sym, data in per_symbol.items():
        s = data.get("stats") or {}
        total_trades += s.get("n_trades", 0) or 0
        total_r      += s.get("total_r", 0.0) or 0.0
        total_wins   += s.get("n_wins", 0) or 0
        gw           += s.get("gross_win_r", 0.0)  or 0.0
        gl           += s.get("gross_loss_r", 0.0) or 0.0

    overall = {
        "n_trades": total_trades,
        "total_r": round(total_r, 3),
        "win_rate": round(total_wins / total_trades, 3) if total_trades else 0.0,
        "gross_win_r":  round(gw, 3),
        "gross_loss_r": round(gl, 3),
        "profit_factor": round(gw / gl, 3) if gl > 0 else (None if gw == 0 else float("inf")),
        "n_symbols": len(per_symbol),
    }
    return {"per_symbol": per_symbol, "overall": overall,
            "timeframe": req.timeframe, "bars_limit": req.bars_limit}
