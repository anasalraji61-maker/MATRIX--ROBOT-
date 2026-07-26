"""V11 preliminary score for all symbols before deep analysis / council."""
from __future__ import annotations

from typing import Any


def score_symbol(
    symbol: str,
    ind: dict,
    mtf: dict | None = None,
    ict: dict | None = None,
    vol: dict | None = None,
    analysis: dict | None = None,
) -> dict[str, Any]:
    mtf = mtf or {}
    ict = ict or {}
    vol = vol or {}
    analysis = analysis or {}

    rsi = float(ind.get("rsi_14") or 50)
    adx = float(ind.get("adx_14") or 0)
    trend = str(ind.get("trend") or "neutral").lower()
    macd_hist = float(ind.get("macd_hist") or 0)
    signal = str(analysis.get("signal") or "HOLD").upper()
    strength = float(analysis.get("strength") or 0)

    momentum = 0.0
    if 30 <= rsi <= 70:
        momentum += 0.1
    else:
        momentum += 0.2
    momentum += min(0.2, abs(macd_hist) * 40)

    trend_score = 0.15 if trend in ("bullish", "bearish") else 0.0
    trend_score += min(0.25, adx / 60)

    mtf_bonus = 0.0
    consensus = str(mtf.get("consensus") or "neutral").lower()
    if consensus in ("bullish", "bearish"):
        mtf_bonus = 0.15

    ict_bonus = min(0.2, int(ict.get("confluence_count") or 0) * 0.05)
    vol_regime = str(vol.get("regime") or "normal").lower()
    vol_bonus = 0.1 if vol_regime in ("high", "expanding") else 0.0

    action_bonus = 0.0
    if signal in ("BUY", "SELL"):
        action_bonus = strength * 0.35

    total = min(1.0, momentum + trend_score + mtf_bonus + ict_bonus + vol_bonus + action_bonus)
    bias = signal if signal in ("BUY", "SELL") else (
        "BUY" if trend == "bullish" or macd_hist > 0 else (
            "SELL" if trend == "bearish" or macd_hist < 0 else "HOLD"
        )
    )
    return {
        "symbol": symbol,
        "preliminary_score": round(total, 4),
        "bias": bias,
        "signal": signal,
        "strength": strength,
        "adx": adx,
        "trend": trend,
    }


def rank_all_symbols(state: dict) -> list[dict]:
    indicators = state.get("indicators") or {}
    mtf_map = state.get("mtf") or {}
    ict_map = state.get("ict") or {}
    vol_map = state.get("volatility_regimes") or {}
    analyses = {a["symbol"]: a for a in (state.get("analyses") or []) if a.get("symbol")}

    ranked: list[dict] = []
    for sym, ind in indicators.items():
        if not ind:
            continue
        ranked.append(score_symbol(
            sym, ind,
            mtf_map.get(sym),
            ict_map.get(sym),
            vol_map.get(sym),
            analyses.get(sym),
        ))
    ranked.sort(key=lambda x: x["preliminary_score"], reverse=True)
    return ranked
