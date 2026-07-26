"""
VectorBT backtest — same Matrix signals as backtest/engine.py, richer metrics.

Requires: pip install -r requirements-backtest.txt
CPU-only (no GPU). Typical runtime: 2000 H1 bars ~30-60s first run (numba compile).
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

import numpy as np
import pandas as pd

from backtest.engine import (
    MIN_WARMUP_BARS,
    SIGNAL_THRESHOLD,
    SL_ATR_MULT,
    TP_RR,
    _score_bar,
)
from tools import indicators as _ind
from tools import ict_smc as _ict
from tools import twelve_data

logger = logging.getLogger("matrix.backtest.vectorbt")


@dataclass
class VectorBTResult:
    symbol: str
    timeframe: str
    bars_count: int
    engine: str = "vectorbt"
    stats: dict[str, Any] = field(default_factory=dict)
    compare_engine: dict[str, Any] = field(default_factory=dict)


def _require_vectorbt():
    try:
        import vectorbt as vbt  # noqa: F401
    except ImportError as e:
        raise RuntimeError(
            "vectorbt not installed. On VPS run:\n"
            "  .\\.venv\\Scripts\\pip install -r requirements-backtest.txt"
        ) from e


async def _fetch_bars(symbol: str, bars_limit: int, timeframe: str) -> list[dict]:
    symbol = symbol.upper()
    bars = await twelve_data.fetch_historical(symbol, limit=bars_limit, timeframe=timeframe)
    return symbol, bars


def _build_signal_frames(bars: list[dict], symbol: str) -> pd.DataFrame:
    """Bar-by-bar signals — identical scoring to engine.py (no look-ahead)."""
    n = len(bars)
    idx = pd.RangeIndex(n)
    close = pd.Series([b["close"] for b in bars], index=idx, dtype=float)
    long_e = np.zeros(n, dtype=bool)
    short_e = np.zeros(n, dtype=bool)
    sl_pct = np.full(n, np.nan, dtype=float)
    tp_pct = np.full(n, np.nan, dtype=float)

    for t in range(MIN_WARMUP_BARS, n):
        window = bars[: t + 1]
        try:
            ind = _ind.compute_indicators(symbol, window).model_dump()
            ict = _ict.analyze(symbol, window, backtest_mode=True).model_dump()
        except Exception as e:
            logger.debug("signal bar %s: %s", t, e)
            continue

        norm = _score_bar(ind, ict)
        atr = ind.get("atr_14") or 0.0
        price = bars[t]["close"]
        if atr <= 0 or price <= 0:
            continue

        sl_dist = max(atr * SL_ATR_MULT, price * 0.0005)
        sl_p = sl_dist / price
        tp_p = sl_dist * TP_RR / price

        if norm >= SIGNAL_THRESHOLD:
            long_e[t] = True
            sl_pct[t] = sl_p
            tp_pct[t] = tp_p
        elif norm <= -SIGNAL_THRESHOLD:
            short_e[t] = True
            sl_pct[t] = sl_p
            tp_pct[t] = tp_p

    return pd.DataFrame(
        {"close": close, "long": long_e, "short": short_e, "sl_pct": sl_pct, "tp_pct": tp_pct},
        index=idx,
    )


def _run_vectorbt(df: pd.DataFrame, timeframe: str) -> dict[str, Any]:
    import vectorbt as vbt

    freq_map = {"M15": "15min", "H1": "1h", "H4": "4h", "D1": "1D"}
    freq = freq_map.get(timeframe.upper(), "1h")

    close = df["close"]
    sl = df["sl_pct"].ffill().fillna(0.015)
    tp = df["tp_pct"].ffill().fillna(0.03)

    pf = vbt.Portfolio.from_signals(
        close,
        entries=df["long"],
        short_entries=df["short"],
        sl_stop=sl,
        tp_stop=tp,
        freq=freq,
        init_cash=10_000,
        fees=0.0,
        slippage=0.0,
    )

    raw = pf.stats()
    stats: dict[str, Any] = {}
    for k, v in raw.items():
        if isinstance(v, (np.floating, float)):
            stats[str(k)] = round(float(v), 4) if np.isfinite(v) else None
        elif isinstance(v, (np.integer, int)):
            stats[str(k)] = int(v)
        else:
            stats[str(k)] = str(v)

    stats["total_trades"] = int(pf.trades.count())
    stats["win_rate"] = round(float(pf.trades.win_rate()), 4) if pf.trades.count() else 0.0
    stats["profit_factor"] = (
        round(float(pf.trades.profit_factor()), 4)
        if pf.trades.count() and np.isfinite(pf.trades.profit_factor())
        else None
    )
    stats["max_drawdown_pct"] = round(float(pf.max_drawdown() * 100), 2)
    stats["sharpe_ratio"] = (
        round(float(pf.sharpe_ratio()), 4)
        if np.isfinite(pf.sharpe_ratio())
        else None
    )
    stats["total_return_pct"] = round(float(pf.total_return() * 100), 2)
    return stats


async def run_vectorbt_backtest(
    symbol: str,
    bars_limit: int = 2000,
    timeframe: str = "H1",
    *,
    compare_builtin: bool = True,
) -> VectorBTResult:
    """Run VectorBT portfolio simulation on Matrix rule signals."""
    _require_vectorbt()
    symbol, bars = await _fetch_bars(symbol, bars_limit, timeframe)
    n = len(bars)
    if n < MIN_WARMUP_BARS + 50:
        return VectorBTResult(
            symbol=symbol,
            timeframe=timeframe,
            bars_count=n,
            stats={"error": f"Not enough bars: got {n}, need ≥{MIN_WARMUP_BARS + 50}"},
        )

    df = _build_signal_frames(bars, symbol)
    try:
        stats = _run_vectorbt(df, timeframe)
    except Exception as e:
        logger.exception("vectorbt run failed for %s", symbol)
        return VectorBTResult(
            symbol=symbol,
            timeframe=timeframe,
            bars_count=n,
            stats={"error": f"{type(e).__name__}: {e}"},
        )

    compare: dict[str, Any] = {}
    if compare_builtin:
        from backtest.engine import run_backtest

        builtin = await run_backtest(symbol, bars_limit=bars_limit, timeframe=timeframe)
        compare = {"engine": "builtin", "stats": builtin.stats}

    return VectorBTResult(
        symbol=symbol,
        timeframe=timeframe,
        bars_count=n,
        stats=stats,
        compare_engine=compare,
    )
