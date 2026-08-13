"""V11 cheap technical scanner — all symbols, no LLM."""
from __future__ import annotations

import logging
from typing import Any

from config import get_settings
from tools.data_quality import symbol_quarantine_reason
from tools.liquidity_guard import check_spread
from tools.scalping_guard import scanner_universe, scalping_asset_allowed

logger = logging.getLogger("matrix.cheap_scanner")


def _cheap_score(ind: dict) -> tuple[float, str]:
    """Lightweight 0–1 score from existing indicator snapshot."""
    if not ind:
        return 0.0, "no_data"
    rsi = float(ind.get("rsi_14") or 50)
    adx = float(ind.get("adx_14") or 0)
    trend = str(ind.get("trend") or "neutral").lower()
    macd_hist = float(ind.get("macd_hist") or 0)
    stoch_k = float(ind.get("stoch_k") or 50)

    momentum = 0.0
    if rsi < 35 or rsi > 65:
        momentum += 0.15
    if abs(macd_hist) > 0:
        momentum += min(0.2, abs(macd_hist) * 50)
    if stoch_k < 25 or stoch_k > 75:
        momentum += 0.1

    trend_score = 0.0
    if trend in ("bullish", "bearish"):
        trend_score += 0.25
    if adx >= 18:
        trend_score += min(0.25, adx / 80)

    vol = str(ind.get("volatility_regime") or "normal").lower()
    vol_bonus = 0.1 if vol in ("high", "expanding") else 0.0

    score = min(1.0, momentum + trend_score + vol_bonus)
    bias = "bullish" if (trend == "bullish" or macd_hist > 0) else (
        "bearish" if (trend == "bearish" or macd_hist < 0) else "neutral"
    )
    return round(score, 4), bias


def run_cheap_scan(
    state: dict,
    *,
    symbols: list[str] | None = None,
) -> dict[str, Any]:
    settings = get_settings()
    mode = state.get("mode") or settings.trading_state
    universe = symbols or scanner_universe(settings)
    indicators_map = state.get("indicators") or {}
    quotes = (state.get("market_data") or {}).get("quotes", [])
    quote_map = {q["symbol"]: q for q in quotes}

    scanned: list[str] = []
    ranked: list[dict] = []
    rejected: dict[str, str] = {}

    for sym in universe:
        scanned.append(sym)
        if not scalping_asset_allowed(sym, settings):
            rejected[sym] = "asset class not allowed for scanner"
            continue
        dq = symbol_quarantine_reason(sym, state, mode)
        if dq:
            rejected[sym] = f"quarantine: {dq}"
            continue
        spread_ok, spread_reason = check_spread(sym, quote_map.get(sym), settings)
        if not spread_ok:
            rejected[sym] = spread_reason
            continue
        ind = indicators_map.get(sym)
        if not ind:
            rejected[sym] = "no indicator data in state"
            continue
        score, bias = _cheap_score(ind)
        if score < 0.15:
            rejected[sym] = f"low cheap score {score:.2f}"
            continue
        ranked.append({
            "symbol": sym,
            "cheap_score": score,
            "bias": bias,
            "rsi_14": ind.get("rsi_14"),
            "adx_14": ind.get("adx_14"),
            "trend": ind.get("trend"),
        })

    ranked.sort(key=lambda x: x["cheap_score"], reverse=True)
    top_deep = max(1, int(getattr(settings, "cheap_scan_top_deep", 10)))

    return {
        "scanned_symbols_count": len(scanned),
        "cheap_candidates_count": len(ranked),
        "cheap_ranked": ranked,
        "top_deep_symbols": [r["symbol"] for r in ranked[:top_deep]],
        "cheap_scan_rejected": rejected,
    }
