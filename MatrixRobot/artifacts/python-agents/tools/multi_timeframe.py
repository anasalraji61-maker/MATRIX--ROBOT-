"""
Multi-Timeframe (MTF) trend analysis.

For each symbol, fetch bars on M15, H1, H4, D1 and compute a lightweight
trend score per timeframe. Combine into a consensus view:

    score in [-1.0, +1.0]:
        +1.0 = all 4 TFs bullish
         0.0 = mixed
        -1.0 = all 4 TFs bearish

    consensus:
        "bullish"  if score >=  0.5 and aligned_count >= 3
        "bearish"  if score <= -0.5 and aligned_count >= 3
        "mixed"    if both bull and bear TFs present
        "neutral"  otherwise
"""
from __future__ import annotations

import asyncio
import pandas as pd
import ta

from tools.twelve_data import fetch_historical
from models.schemas import MultiTimeframeView, TimeframeTrend


TIMEFRAMES: list[tuple[str, int]] = [
    ("M15", 80),
    ("H1", 120),
    ("H4", 80),
    ("D1", 60),
]


def _tf_trend(bars: list[dict]) -> TimeframeTrend:
    if len(bars) < 30:
        return TimeframeTrend(timeframe="?", trend="neutral")
    df = pd.DataFrame(bars, columns=["open", "high", "low", "close", "volume"])
    close = df["close"]
    high = df["high"]
    low = df["low"]
    try:
        ema20 = ta.trend.EMAIndicator(close, window=20).ema_indicator().dropna().iloc[-1]
        ema50 = ta.trend.EMAIndicator(close, window=50).ema_indicator().dropna().iloc[-1]
        rsi = ta.momentum.RSIIndicator(close, window=14).rsi().dropna().iloc[-1]
        adx = ta.trend.ADXIndicator(high, low, close, window=14).adx().dropna().iloc[-1]
    except Exception:
        return TimeframeTrend(timeframe="?", trend="neutral")

    last = float(close.iloc[-1])
    bull = 0
    bear = 0
    if ema20 > ema50 and last > ema20:
        bull += 2
    elif ema20 < ema50 and last < ema20:
        bear += 2
    if rsi > 55:
        bull += 1
    elif rsi < 45:
        bear += 1
    if adx >= 25:
        # ADX confirms whichever side already leads
        if bull > bear:
            bull += 1
        elif bear > bull:
            bear += 1

    if bull - bear >= 2:
        label = "bullish"
    elif bear - bull >= 2:
        label = "bearish"
    else:
        label = "neutral"

    return TimeframeTrend(
        timeframe="?",
        trend=label,
        rsi_14=round(float(rsi), 2),
        adx_14=round(float(adx), 2),
    )


async def compute_mtf(symbol: str, h1_bars: list[dict] | None = None) -> MultiTimeframeView:
    """Fetch timeframes and return consensus view. Reuse h1_bars when provided."""
    fetch_plan = [(tf, lim) for tf, lim in TIMEFRAMES if not (tf == "H1" and h1_bars)]
    results = []
    if fetch_plan:
        fetched = await asyncio.gather(
            *[fetch_historical(symbol, limit=lim, timeframe=tf) for tf, lim in fetch_plan]
        )
        results = list(fetched)

    tf_trends: list[TimeframeTrend] = []
    bull_n = 0
    bear_n = 0
    for tf, lim in TIMEFRAMES:
        if tf == "H1" and h1_bars is not None:
            bars = h1_bars
        else:
            idx = next(i for i, (t, _) in enumerate(fetch_plan) if t == tf)
            bars = results[idx]
        t = _tf_trend(bars)
        t.timeframe = tf
        tf_trends.append(t)
        if t.trend == "bullish":
            bull_n += 1
        elif t.trend == "bearish":
            bear_n += 1

    from config import get_settings
    required = max(2, get_settings().mtf_required_alignment)
    n = len(tf_trends)
    score = round((bull_n - bear_n) / max(n, 1), 3)
    aligned = max(bull_n, bear_n)
    # Need score signal AND configurable # of TFs aligned on that side
    if bull_n >= required and bull_n > bear_n:
        consensus = "bullish"
    elif bear_n >= required and bear_n > bull_n:
        consensus = "bearish"
    elif bull_n > 0 and bear_n > 0:
        consensus = "mixed"
    else:
        consensus = "neutral"

    return MultiTimeframeView(
        symbol=symbol,
        timeframes=tf_trends,
        consensus=consensus,
        aligned_count=aligned,
        score=score,
    )


def format_mtf_summary(mtf: MultiTimeframeView) -> str:
    cells = [f"{t.timeframe}={t.trend[:4].upper()}" for t in mtf.timeframes]
    return (
        f"MTF[{mtf.symbol}]: " + " ".join(cells) +
        f" → consensus={mtf.consensus.upper()} score={mtf.score:+.2f}"
    )
