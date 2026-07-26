"""V11 rule-based scalping strategies — M5/M15 indicators, no LLM."""
from __future__ import annotations

from typing import Any


def _sig(signal: str, strength: float, strategy: str, rr: float, reasons: list[str]) -> dict | None:
    if signal not in ("BUY", "SELL") or strength < 0.5:
        return None
    return {
        "signal": signal,
        "strength": round(min(1.0, strength), 4),
        "strategy": strategy,
        "estimated_rr": round(rr, 2),
        "reasons": reasons,
    }


def ema_pullback_scalp(ind: dict, mtf: dict | None = None) -> dict | None:
    ema20 = ind.get("ema_20")
    ema50 = ind.get("ema_50")
    close = ind.get("close") or ind.get("last_close")
    rsi = float(ind.get("rsi_14") or 50)
    if not all(v is not None for v in (ema20, ema50, close)):
        return None
    ema20, ema50, close = float(ema20), float(ema50), float(close)
    if ema20 > ema50 and close <= ema20 * 1.0003 and 40 <= rsi <= 55:
        return _sig("BUY", 0.62 + (55 - rsi) / 100, "ema_pullback_scalp", 1.3,
                      ["EMA20>EMA50", "pullback to EMA20", f"RSI={rsi:.0f}"])
    if ema20 < ema50 and close >= ema20 * 0.9997 and 45 <= rsi <= 60:
        return _sig("SELL", 0.62 + (rsi - 45) / 100, "ema_pullback_scalp", 1.3,
                      ["EMA20<EMA50", "pullback to EMA20", f"RSI={rsi:.0f}"])
    return None


def micro_breakout_scalp(ind: dict, bars: list[dict] | None = None) -> dict | None:
    if not bars or len(bars) < 20:
        return None
    highs = [float(b.get("high", b[1] if isinstance(b, (list, tuple)) else 0)) for b in bars[-20:]]
    lows = [float(b.get("low", b[2] if isinstance(b, (list, tuple)) else 0)) for b in bars[-20:]]
    last = bars[-1]
    close = float(last.get("close", last[3] if isinstance(last, (list, tuple)) else 0))
    prev_high = max(highs[:-1])
    prev_low = min(lows[:-1])
    adx = float(ind.get("adx_14") or 0)
    if close > prev_high and adx >= 15:
        return _sig("BUY", 0.65 + min(0.15, adx / 100), "micro_breakout", 1.4,
                      ["break above 20-bar high", f"ADX={adx:.0f}"])
    if close < prev_low and adx >= 15:
        return _sig("SELL", 0.65 + min(0.15, adx / 100), "micro_breakout", 1.4,
                      ["break below 20-bar low", f"ADX={adx:.0f}"])
    return None


def asian_range_mean_reversion(ind: dict, session_kz: str = "") -> dict | None:
    if session_kz != "asian":
        return None
    rsi = float(ind.get("rsi_14") or 50)
    stoch_k = float(ind.get("stoch_k") or 50)
    bb_pos = str(ind.get("bb_position") or "").lower()
    if rsi <= 32 and stoch_k <= 25:
        return _sig("BUY", 0.64, "asian_range_mean_reversion", 1.2,
                      ["Asian range", "RSI/Stoch oversold", bb_pos or "BB lower zone"])
    if rsi >= 68 and stoch_k >= 75:
        return _sig("SELL", 0.64, "asian_range_mean_reversion", 1.2,
                      ["Asian range", "RSI/Stoch overbought", bb_pos or "BB upper zone"])
    return None


def liquidity_sweep_reversal(ind: dict, ict: dict | None = None) -> dict | None:
    ict = ict or {}
    sweep = str(ict.get("liquidity_sweep") or ict.get("last_sweep") or "").lower()
    bias = str(ict.get("bias") or "").lower()
    if "bullish" in sweep or (bias == "bullish" and ict.get("choch")):
        return _sig("BUY", 0.68, "liquidity_sweep_reversal", 1.5,
                      ["ICT liquidity sweep / CHoCH bullish"])
    if "bearish" in sweep or (bias == "bearish" and ict.get("choch")):
        return _sig("SELL", 0.68, "liquidity_sweep_reversal", 1.5,
                      ["ICT liquidity sweep / CHoCH bearish"])
    return None


def volatility_expansion_scalp(ind: dict) -> dict | None:
    bb_width = float(ind.get("bb_width_pct") or 0)
    atr = float(ind.get("atr_14") or 0)
    trend = str(ind.get("trend") or "").lower()
    if bb_width < 0.8 or atr <= 0:
        return None
    macd_hist = float(ind.get("macd_hist") or 0)
    if trend == "bullish" and macd_hist > 0:
        return _sig("BUY", 0.63 + min(0.12, bb_width / 20), "volatility_expansion_scalp", 1.35,
                      ["BB width expanding", "bullish trend", "MACD positive"])
    if trend == "bearish" and macd_hist < 0:
        return _sig("SELL", 0.63 + min(0.12, bb_width / 20), "volatility_expansion_scalp", 1.35,
                      ["BB width expanding", "bearish trend", "MACD negative"])
    return None


def trend_continuation_m5(ind: dict, mtf: dict | None = None) -> dict | None:
    mtf = mtf or {}
    m5 = (mtf.get("M5") or mtf.get("m5") or {})
    m15 = (mtf.get("M15") or mtf.get("m15") or {})
    m5_trend = str(m5.get("trend") or ind.get("trend") or "").lower()
    m15_trend = str(m15.get("trend") or "").lower()
    adx = float(ind.get("adx_14") or 0)
    if adx < 20:
        return None
    if m5_trend == "bullish" and m15_trend in ("bullish", "neutral", ""):
        return _sig("BUY", 0.66 + min(0.1, adx / 100), "trend_continuation_m5", 1.4,
                      ["M5/M15 bullish alignment", f"ADX={adx:.0f}"])
    if m5_trend == "bearish" and m15_trend in ("bearish", "neutral", ""):
        return _sig("SELL", 0.66 + min(0.1, adx / 100), "trend_continuation_m5", 1.4,
                      ["M5/M15 bearish alignment", f"ADX={adx:.0f}"])
    return None


STRATEGIES = (
    ema_pullback_scalp,
    micro_breakout_scalp,
    asian_range_mean_reversion,
    liquidity_sweep_reversal,
    volatility_expansion_scalp,
    trend_continuation_m5,
)


def evaluate_all(
    symbol: str,
    ind: dict,
    *,
    bars: list[dict] | None = None,
    mtf: dict | None = None,
    ict: dict | None = None,
    session_kz: str = "",
) -> list[dict]:
    hits: list[dict] = []
    for fn in STRATEGIES:
        try:
            if fn is micro_breakout_scalp:
                hit = fn(ind, bars)
            elif fn is asian_range_mean_reversion:
                hit = fn(ind, session_kz)
            elif fn is liquidity_sweep_reversal:
                hit = fn(ind, ict)
            elif fn is trend_continuation_m5:
                hit = fn(ind, mtf)
            else:
                hit = fn(ind, mtf)
        except Exception:
            hit = None
        if hit:
            hit["symbol"] = symbol
            hits.append(hit)
    hits.sort(key=lambda x: x["strength"], reverse=True)
    return hits


def best_signal(candidates: list[dict]) -> dict | None:
    return candidates[0] if candidates else None
