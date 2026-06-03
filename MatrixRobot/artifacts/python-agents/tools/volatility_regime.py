"""
Volatility regime classifier.

Computes ATR(14) over the recent history of a symbol, then ranks the latest
value as a percentile of its own lookback window. From that:

    percentile < 25  →  "low"     → size_multiplier 1.20  (calm market, can size up modestly)
    percentile > 75  →  "high"    → size_multiplier 0.60  (volatile, size down)
    otherwise        →  "normal"  → size_multiplier 1.00

Output is used by the risk agent to scale position size, and by the
analysis agent as a regime tag fed into the LLM prompt.
"""
from __future__ import annotations

import pandas as pd
import ta

from models.schemas import VolatilityRegime


def classify(symbol: str, bars: list[dict]) -> VolatilityRegime:
    if len(bars) < 30:
        return VolatilityRegime(symbol=symbol, regime="normal", size_multiplier=1.0)

    df = pd.DataFrame(bars, columns=["open", "high", "low", "close", "volume"])
    try:
        atr_series = ta.volatility.AverageTrueRange(
            df["high"], df["low"], df["close"], window=14
        ).average_true_range().dropna()
        if atr_series.empty:
            return VolatilityRegime(symbol=symbol, regime="normal", size_multiplier=1.0)

        latest = float(atr_series.iloc[-1])
        lookback = atr_series.iloc[-min(100, len(atr_series)):]
        rank = float((lookback <= latest).mean()) * 100  # percentile 0..100

        if rank < 25:
            regime, mult = "low", 1.20
        elif rank > 75:
            regime, mult = "high", 0.60
        else:
            regime, mult = "normal", 1.00

        return VolatilityRegime(
            symbol=symbol,
            atr_14=round(latest, 6),
            atr_percentile=round(rank, 1),
            regime=regime,
            size_multiplier=mult,
        )
    except Exception:
        return VolatilityRegime(symbol=symbol, regime="normal", size_multiplier=1.0)
