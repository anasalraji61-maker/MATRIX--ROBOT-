"""Cheap off-session market scanner — no Claude unless escalation criteria met."""
from __future__ import annotations

import logging
from typing import Any

from config import get_settings
from tools.data_quality import symbol_quarantine_reason
from tools.liquidity_guard import check_spread
from tools.symbol_registry import asset_class
from tools import trade_tiers

logger = logging.getLogger("matrix.off_session_scanner")

FX_MAJORS = frozenset({
    "EURUSD", "GBPUSD", "USDJPY", "USDCHF", "AUDUSD", "NZDUSD", "USDCAD",
})


def _tradable_symbols(state: dict, settings) -> list[str]:
    symbols = state.get("symbols_analyzed") or settings.symbol_list
    mode = state.get("mode") or getattr(settings, "trading_state", "PAPER_MODE")
    out: list[str] = []
    for sym in symbols:
        s = str(sym).upper()
        if symbol_quarantine_reason(s, state, mode):
            continue
        if getattr(settings, "off_session_scan_fx_only", True):
            if asset_class(s) != "fx":
                continue
        out.append(s)
    return out


def _estimate_rr(ind: dict) -> float:
    atr = float(ind.get("atr_14") or 0.001)
    if atr <= 0:
        return 0.0
    return 2.0


async def run_scan(
    state: dict,
    *,
    escalate: bool = True,
) -> dict[str, Any]:
    """Run ensemble scan; optionally escalate top setups to per-symbol LLM."""
    from agents.analysis_agent import _ensemble_analysis, _pick_best_signal

    settings = get_settings()
    mode = state.get("mode", settings.trading_state)
    symbols = _tradable_symbols(state, settings)
    indicators_map = state.get("indicators", {})
    mtf_map = state.get("mtf", {})
    ict_map = state.get("ict", {})
    vol_map = state.get("volatility_regimes", {})
    sentiment = state.get("sentiment") or {}
    quotes = (state.get("market_data") or {}).get("quotes", [])
    quote_map = {q["symbol"]: q for q in quotes}

    min_strength = float(getattr(settings, "off_session_escalation_min_strength", 0.75))
    max_escalate = int(getattr(settings, "off_session_max_brain_escalations", 3))

    scanned: list[str] = []
    candidates: list[dict] = []
    rejected: dict[str, str] = {}
    escalated_symbols: list[str] = []
    analyses: list[dict] = []

    for sym in symbols:
        scanned.append(sym)
        ind = indicators_map.get(sym, {})
        if not ind:
            rejected[sym] = "no indicator data"
            continue

        spread_ok, spread_reason = check_spread(sym, quote_map.get(sym), settings)
        if not spread_ok:
            rejected[sym] = spread_reason
            continue

        result = _ensemble_analysis(
            sym,
            ind,
            mtf_map.get(sym, {}),
            ict_map.get(sym, {}),
            vol_map.get(sym, {}),
            sentiment,
        )
        ad = result.model_dump()
        analyses.append(ad)

        signal = str(ad.get("signal", "HOLD")).upper()
        strength = float(ad.get("strength") or 0.0)
        if signal not in ("BUY", "SELL") or strength < min_strength:
            continue

        tier = trade_tiers.classify_trade_tier(strength, settings)
        if tier == "HOLD":
            continue

        rr = _estimate_rr(ind)
        min_rr = trade_tiers.rr_minimum_for_tier(tier, settings)
        if rr < min_rr:
            rejected[sym] = f"R/R {rr:.2f} < {min_rr}"
            continue

        candidates.append({
            "symbol": sym,
            "signal": signal,
            "strength": strength,
            "trade_tier": tier,
            "source": "ensemble_scanner",
            "rr_estimate": rr,
        })

    # Escalate top candidates to LLM (per-symbol, not full agentic brain)
    escalated_analyses: list[dict] = []
    if escalate and settings.has_llm and candidates:
        from agents import analysis_agent

        candidates.sort(key=lambda c: c["strength"], reverse=True)
        for cand in candidates[:max_escalate]:
            sym = cand["symbol"]
            ind = indicators_map.get(sym, {})
            try:
                llm_result = await analysis_agent._llm_analysis(
                    sym,
                    ind,
                    state.get("indicators_summaries", {}).get(sym, ""),
                    mtf_map.get(sym, {}),
                    state.get("mtf_summaries", {}).get(sym, ""),
                    ict_map.get(sym, {}),
                    state.get("ict_summaries", {}).get(sym, ""),
                    vol_map.get(sym, {}),
                    sentiment,
                    settings,
                )
                escalated_analyses.append(llm_result.model_dump())
                escalated_symbols.append(sym)
                for i, a in enumerate(analyses):
                    if a.get("symbol") == sym:
                        analyses[i] = llm_result.model_dump()
                        break
            except Exception as e:
                logger.warning("Escalation failed for %s: %s", sym, e)

    best = _pick_best_signal(analyses) if analyses else {}

    return {
        "analyses": analyses,
        "best_analysis": best,
        "off_session_scanned_symbols": scanned,
        "off_session_candidates": candidates,
        "off_session_escalated_to_brain": escalated_symbols,
        "off_session_scan_rejected": rejected,
        "brain_escalation_count": len(escalated_symbols),
    }
