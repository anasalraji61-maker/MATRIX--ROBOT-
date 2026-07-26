"""V11 Matrix Trading Council — 7 minds + Meta Judge (infographic architecture)."""
from __future__ import annotations

import logging
from typing import Any

from config import get_settings
from models.council_schemas import BrainOutput, MetaJudgeOutput
from tools.liquidity_guard import spread_pips
from tools.session_engine import get_profile
from tools.strategy_router import route_market_mode

logger = logging.getLogger("matrix.trading_council")

BRAIN_WEIGHTS = {
    "market_regime": 0.12,
    "technical_quant": 0.18,
    "ict_price_action": 0.15,
    "scalping": 0.12,
    "news_macro": 0.10,
    "strategy_router": 0.13,
    "skeptic": 0.12,
    "risk_prop": 0.08,
}


def _clamp(v: float) -> float:
    return max(-1.0, min(1.0, round(v, 3)))


def _sig_to_str(signal: str) -> str:
    s = str(signal or "HOLD").upper()
    if s == "BUY":
        return "buy"
    if s == "SELL":
        return "sell"
    if s in ("REJECT", "VETO"):
        return "reject"
    return "hold"


def _brain_dict(b: BrainOutput) -> dict:
    return b.model_dump()


def market_regime_brain(state: dict, candidate: dict, settings=None) -> BrainOutput:
    sym = candidate["symbol"]
    vol = (state.get("volatility_regimes") or {}).get(sym, {})
    regime = str(vol.get("regime") or "normal").lower()
    session = state.get("session_profile") or get_profile(settings or get_settings())
    signal = str(candidate.get("signal", "HOLD")).upper()
    kz = session.get("active_killzone", "none")
    liquidity = session.get("liquidity", "low")
    news_blackout = bool(session.get("news_blackout", False))

    score = 0.0
    notes: list[str] = []
    if regime in ("high", "expanding"):
        score += 0.35
        notes.append(f"vol={regime}")
    elif regime == "low":
        score -= 0.15
        notes.append("low volatility")
    if kz in ("london", "newyork"):
        score += 0.25
    elif kz == "asian":
        score += 0.1
    else:
        score -= 0.1
        notes.append("off-session liquidity")
    if news_blackout:
        score = -0.8
        notes.append("news blackout")
    if signal in ("BUY", "SELL") and score > 0:
        score += 0.1

    veto = news_blackout
    return BrainOutput(
        brain="market_regime",
        symbol=sym,
        signal="reject" if veto else _sig_to_str(signal),
        score=_clamp(score),
        confidence=0.7,
        suggested_strategy="intraday" if kz in ("london", "newyork") else "scalp",
        suggested_tier="small" if score > 0.3 else "watch",
        veto=veto,
        veto_reason="news blackout" if veto else "",
        short_reason=f"regime={regime} kz={kz} liq={liquidity}",
        risk_notes=notes,
    )


def technical_quant_brain(state: dict, candidate: dict) -> BrainOutput:
    sym = candidate["symbol"]
    ind = (state.get("indicators") or {}).get(sym, {})
    mtf = (state.get("mtf") or {}).get(sym, {})
    signal = str(candidate.get("signal", "HOLD")).upper()

    rsi = float(ind.get("rsi_14") or 50)
    adx = float(ind.get("adx_14") or 0)
    macd_hist = float(ind.get("macd_hist") or 0)
    bb_width = float(ind.get("bb_width_pct") or 0)
    ichimoku = str(ind.get("ichimoku_position") or ind.get("above_cloud") or "")
    mtf_align = int(mtf.get("aligned_count") or 0)

    score = float(candidate.get("strength") or 0) - 0.5
    notes: list[str] = []
    if signal == "BUY":
        if rsi < 65:
            score += 0.2
        if macd_hist > 0:
            score += 0.15
    elif signal == "SELL":
        if rsi > 35:
            score += 0.2
        if macd_hist < 0:
            score += 0.15
    score += min(0.25, adx / 50)
    score += min(0.15, mtf_align * 0.05)
    if bb_width > 1.0:
        score += 0.05
        notes.append("BB expanding")

    return BrainOutput(
        brain="technical_quant",
        symbol=sym,
        signal=_sig_to_str(signal),
        score=_clamp(score),
        confidence=min(0.95, 0.5 + adx / 100),
        suggested_strategy="trend_continuation" if adx >= 22 else "range_reversal",
        suggested_tier="normal" if score > 0.4 else "small",
        short_reason=f"RSI={rsi:.0f} ADX={adx:.0f} MTF_align={mtf_align}",
        risk_notes=notes,
    )


def ict_price_action_brain(state: dict, candidate: dict) -> BrainOutput:
    sym = candidate["symbol"]
    ict = (state.get("ict") or {}).get(sym, {})
    signal = str(candidate.get("signal", "HOLD")).upper()
    bias = str(ict.get("bias") or "neutral").lower()
    conf = int(ict.get("confluence_count") or 0)
    bos = bool(ict.get("bos") or ict.get("last_bos"))
    choch = bool(ict.get("choch") or ict.get("last_choch"))
    fvg = bool(ict.get("fvg") or ict.get("has_fvg"))
    ob = bool(ict.get("order_block") or ict.get("has_ob"))

    score = 0.0
    notes: list[str] = []
    if signal == "BUY" and "bull" in bias:
        score = 0.45
    elif signal == "SELL" and "bear" in bias:
        score = 0.45
    elif bias == "neutral":
        score = 0.0
    else:
        score = -0.35
    score += min(0.25, conf * 0.08)
    if bos:
        notes.append("BOS")
        score += 0.1
    if choch:
        notes.append("CHoCH")
        score += 0.08
    if fvg:
        notes.append("FVG")
    if ob:
        notes.append("OB")

    return BrainOutput(
        brain="ict_price_action",
        symbol=sym,
        signal=_sig_to_str(signal),
        score=_clamp(score),
        confidence=min(0.9, 0.4 + conf * 0.1),
        suggested_strategy="breakout" if bos else "pullback",
        suggested_tier="small" if score > 0.25 else "watch",
        short_reason=f"ICT bias={bias} conf={conf}",
        risk_notes=notes,
    )


def scalping_brain(state: dict, candidate: dict, settings=None) -> BrainOutput:
    s = settings or get_settings()
    sym = candidate["symbol"]
    signal = str(candidate.get("signal", "HOLD")).upper()
    quotes = (state.get("market_data") or {}).get("quotes", [])
    quote_map = {q["symbol"]: q for q in quotes}
    sp = spread_pips(sym, quote_map.get(sym))
    max_sp = float(s.scalping_max_spread_pips_fx)
    rr = float(candidate.get("estimated_rr") or candidate.get("rr") or 1.2)
    hold = int(candidate.get("expected_hold_minutes") or s.scalping_max_hold_minutes)

    score = 0.0
    veto = False
    veto_reason = ""
    notes: list[str] = []
    if sp is not None:
        if sp > max_sp:
            score = -0.7
            veto = True
            veto_reason = f"spread {sp:.1f}p > {max_sp}"
            notes.append(f"spread_cost_warning={sp:.1f}p")
        elif sp <= max_sp * 0.6:
            score += 0.3
    if rr >= float(s.scalping_min_rr):
        score += 0.2
    if hold <= int(s.scalping_max_hold_minutes):
        score += 0.1
    strat = str(candidate.get("strategy") or candidate.get("strategy_name") or "")
    if "scalp" in strat.lower() or strat:
        score += 0.15

    return BrainOutput(
        brain="scalping",
        symbol=sym,
        signal="reject" if veto else _sig_to_str(signal),
        score=_clamp(score),
        confidence=0.65,
        suggested_strategy="scalp",
        suggested_tier="micro" if rr < 1.2 else "small",
        veto=veto,
        veto_reason=veto_reason,
        short_reason=f"spread={sp} rr={rr} hold={hold}m",
        risk_notes=notes,
    )


def news_macro_brain(state: dict, candidate: dict) -> BrainOutput:
    sym = candidate["symbol"]
    signal = str(candidate.get("signal", "HOLD")).upper()
    cal = state.get("economic_calendar") or {}
    events = cal.get("upcoming_high_impact") or cal.get("events") or []
    sentiment = state.get("sentiment") or {}
    sent_label = str(sentiment.get("label") or "NEUTRAL").upper()

    score = 0.15
    veto = False
    veto_reason = ""
    notes: list[str] = []
    for ev in events[:8]:
        cur = str(ev.get("currency") or "").upper()
        if cur and cur in sym:
            score = -0.85
            veto = True
            veto_reason = f"high-impact news for {cur}"
            notes.append(veto_reason)
            break
    if signal == "BUY" and sent_label == "POSITIVE":
        score += 0.2
    elif signal == "SELL" and sent_label == "NEGATIVE":
        score += 0.2
    elif sent_label == "NEUTRAL":
        score += 0.05

    return BrainOutput(
        brain="news_macro",
        symbol=sym,
        signal="reject" if veto else _sig_to_str(signal),
        score=_clamp(score),
        confidence=0.6,
        suggested_strategy="no_trade" if veto else "intraday",
        suggested_tier="watch" if veto else "small",
        veto=veto,
        veto_reason=veto_reason,
        short_reason=f"sentiment={sent_label} events={len(events)}",
        risk_notes=notes,
    )


def strategy_router_brain(state: dict, candidate: dict, settings=None) -> BrainOutput:
    s = settings or get_settings()
    route = route_market_mode(s, state.get("session_profile"))
    signal = str(candidate.get("signal", "HOLD")).upper()
    strat = str(candidate.get("strategy") or candidate.get("strategy_name") or "ensemble")

    if not route.get("scalping_allowed") and "scalp" in strat.lower():
        return BrainOutput(
            brain="strategy_router",
            symbol=candidate["symbol"],
            signal="hold",
            score=-0.3,
            confidence=0.7,
            suggested_strategy="no_trade",
            veto=True,
            veto_reason=route.get("reason", "session blocks scalping"),
            short_reason=route.get("reason", ""),
        )

    score = 0.2
    style = "intraday"
    if route.get("scalping_allowed") and ("scalp" in strat.lower() or float(candidate.get("strength") or 0) < 0.68):
        style = "scalp"
        score += 0.25
    if route.get("swing_allowed") and float(candidate.get("strength") or 0) >= 0.75:
        style = "swing"
        score += 0.2

    return BrainOutput(
        brain="strategy_router",
        symbol=candidate["symbol"],
        signal=_sig_to_str(signal),
        score=_clamp(score),
        confidence=0.75,
        suggested_strategy=style,
        suggested_tier="small",
        short_reason=f"router primary={route.get('primary_mode')} → {style}",
    )


def skeptic_brain(state: dict, candidate: dict, settings=None) -> BrainOutput:
    sym = candidate["symbol"]
    ind = (state.get("indicators") or {}).get(sym, {})
    signal = str(candidate.get("signal", "HOLD")).upper()
    trend = str(ind.get("trend") or "neutral").lower()
    rsi = float(ind.get("rsi_14") or 50)
    mtf = (state.get("mtf") or {}).get(sym, {})
    h1 = str((mtf.get("H1") or {}).get("trend") or mtf.get("consensus") or "").lower()

    score = 0.0
    veto = False
    veto_reason = ""
    notes: list[str] = []

    if signal == "BUY" and trend == "bearish":
        score -= 0.55
        notes.append("counter-trend")
    elif signal == "SELL" and trend == "bullish":
        score -= 0.55
        notes.append("counter-trend")
    if signal == "BUY" and h1 == "bearish":
        score -= 0.25
    elif signal == "SELL" and h1 == "bullish":
        score -= 0.25
    if signal == "BUY" and rsi > 72:
        score -= 0.35
        notes.append("late entry — overbought")
    elif signal == "SELL" and rsi < 28:
        score -= 0.35
        notes.append("late entry — oversold")

    from tools.currency_exposure import check_exposure_allowed
    ok, exp_reason = check_exposure_allowed(sym, signal, settings=settings)
    if not ok:
        score -= 0.5
        notes.append(exp_reason)
        if "correlation" in exp_reason:
            veto = True
            veto_reason = exp_reason

    if score <= -0.5:
        veto = True
        veto_reason = veto_reason or "; ".join(notes) or "skeptic veto"

    return BrainOutput(
        brain="skeptic",
        symbol=sym,
        signal="reject" if veto else _sig_to_str(signal),
        score=_clamp(score),
        confidence=0.8,
        suggested_strategy="no_trade" if veto else "watch",
        suggested_tier="watch",
        veto=veto,
        veto_reason=veto_reason,
        short_reason="; ".join(notes) if notes else "no major skeptic flags",
        risk_notes=notes,
    )


def risk_prop_brain(state: dict, candidate: dict, settings=None) -> BrainOutput:
    s = settings or get_settings()
    sym = candidate["symbol"]
    signal = str(candidate.get("signal", "HOLD")).upper()
    risk = state.get("risk") or {}
    prop = state.get("prop_status") or {}

    score = 0.25
    veto = False
    veto_reason = ""
    notes: list[str] = []

    if not risk.get("approved", True) and not state.get("approved_risk_trades"):
        score = -0.6
        notes.append("risk not approved")
    if prop and not prop.get("can_trade", True):
        score = -0.9
        veto = True
        veto_reason = prop.get("block_reason", "prop guard")
    daily_dd = float(risk.get("current_daily_drawdown_pct") or 0)
    max_dd = float(getattr(s, "max_daily_drawdown_pct", 4.0))
    if daily_dd > max_dd * 0.7:
        score -= 0.3
        notes.append(f"daily DD elevated {daily_dd:.1f}%")

    rr = float(candidate.get("estimated_rr") or 1.0)
    if rr < 1.0:
        score -= 0.4
        notes.append(f"RR {rr} too low")

    return BrainOutput(
        brain="risk_prop",
        symbol=sym,
        signal="reject" if veto else _sig_to_str(signal),
        score=_clamp(score),
        confidence=0.85,
        suggested_tier="micro",
        veto=veto,
        veto_reason=veto_reason,
        short_reason="; ".join(notes) if notes else "risk/prop ok",
        risk_notes=notes,
    )


def meta_judge(brains: list[BrainOutput], candidate: dict, settings=None) -> MetaJudgeOutput:
    s = settings or get_settings()
    sym = candidate["symbol"]
    signal = str(candidate.get("signal", "HOLD")).upper()

    total_w = 0.0
    weighted = 0.0
    approved_by: list[str] = []
    rejected_by: list[str] = []
    vetoes: list[str] = []

    for b in brains:
        w = BRAIN_WEIGHTS.get(b.brain, 0.1)
        weighted += b.score * w
        total_w += w
        if b.score >= 0.15:
            approved_by.append(b.brain)
        elif b.score <= -0.15:
            rejected_by.append(b.brain)
        if b.veto:
            vetoes.append(f"{b.brain}: {b.veto_reason or b.short_reason}")

    meta_score = weighted / total_w if total_w else 0.0
    hard_veto = any(b.veto for b in brains)

    tier = "WATCH"
    if meta_score >= 0.5:
        tier = "NORMAL"
    elif meta_score >= 0.35:
        tier = "SMALL"
    elif meta_score >= 0.15:
        tier = "MICRO"

    trade_style = "NONE"
    router = next((b for b in brains if b.brain == "strategy_router"), None)
    if router and router.suggested_strategy == "scalp":
        trade_style = "SCALP"
    elif meta_score >= 0.45:
        trade_style = "INTRADAY"
    elif meta_score >= 0.25:
        trade_style = "SWING"

    final_action = "HOLD"
    rejection = ""
    if hard_veto or meta_score < -0.2:
        rejection = "; ".join(vetoes) if vetoes else f"meta_score={meta_score:.2f}"
    elif meta_score >= 0.15 and signal in ("BUY", "SELL") and not hard_veto:
        final_action = signal

    sl_pips = int((float(s.scalping_sl_pips_min) + float(s.scalping_sl_pips_max)) / 2)
    tp_pips = int((float(s.scalping_tp_pips_min) + float(s.scalping_tp_pips_max)) / 2)
    if trade_style == "INTRADAY":
        sl_pips = max(sl_pips, 12)
        tp_pips = max(tp_pips, 20)
    elif trade_style == "SWING":
        sl_pips = max(sl_pips, 25)
        tp_pips = max(tp_pips, 50)

    return MetaJudgeOutput(
        symbol=sym,
        final_action=final_action,
        trade_style=trade_style if final_action != "HOLD" else "NONE",
        tier=tier,
        confidence=round(min(0.98, abs(meta_score) + 0.35), 3),
        meta_score=_clamp(meta_score),
        selected_strategy=str(candidate.get("strategy") or candidate.get("strategy_name") or "ensemble"),
        entry_reason=candidate.get("entry_reason") or candidate.get("reasoning") or "",
        rejection_reason=rejection,
        vetoes=vetoes,
        approved_by=approved_by,
        rejected_by=rejected_by,
        expected_hold_minutes=int(candidate.get("expected_hold_minutes") or s.scalping_max_hold_minutes),
        brains=brains,
    )


def evaluate_candidate(state: dict, candidate: dict, settings=None) -> dict:
    s = settings or get_settings()
    brains = [
        market_regime_brain(state, candidate, s),
        technical_quant_brain(state, candidate),
        ict_price_action_brain(state, candidate),
        scalping_brain(state, candidate, s),
        news_macro_brain(state, candidate),
        strategy_router_brain(state, candidate, s),
        skeptic_brain(state, candidate, s),
        risk_prop_brain(state, candidate, s),
    ]
    meta = meta_judge(brains, candidate, s)
    approved = meta.final_action in ("BUY", "SELL") and not meta.vetoes and meta.meta_score >= 0.15
    return {
        **candidate,
        "council": {
            "meta": meta.model_dump(),
            "meta_score": meta.meta_score,
            "approved": approved,
            "veto": bool(meta.vetoes),
            "brains": [_brain_dict(b) for b in brains],
        },
    }


def candidates_from_analyses(state: dict) -> list[dict]:
    out: list[dict] = []
    for a in state.get("analyses") or []:
        sig = str(a.get("signal", "HOLD")).upper()
        if sig not in ("BUY", "SELL"):
            continue
        out.append({
            "symbol": a["symbol"],
            "signal": sig,
            "strength": float(a.get("strength") or 0),
            "strategy": "ensemble",
            "estimated_rr": 1.5,
            "entry_reason": "; ".join(a.get("reasons") or [])[:200],
            "reasoning": a.get("reasoning", ""),
        })
    out.sort(key=lambda x: x["strength"], reverse=True)
    return out


def run_full_council(state: dict, settings=None) -> dict[str, Any]:
    s = settings or get_settings()
    from tools.preliminary_scorer import rank_all_symbols
    from tools import memory

    ranked = rank_all_symbols(state)
    top_deep = int(getattr(s, "deep_analysis_top_n", 15))
    top_council = int(getattr(s, "council_top_n", 8))

    if getattr(s, "council_full_universe_debug", False):
        pool = candidates_from_analyses(state)
    else:
        deep_syms = {r["symbol"] for r in ranked[:top_deep]}
        pool = [c for c in candidates_from_analyses(state) if c["symbol"] in deep_syms]
        if not pool:
            pool = [
                {
                    "symbol": r["symbol"],
                    "signal": r["bias"] if r["bias"] in ("BUY", "SELL") else "HOLD",
                    "strength": r["preliminary_score"],
                    "strategy": "preliminary",
                    "estimated_rr": 1.3,
                }
                for r in ranked[:top_council]
                if r["bias"] in ("BUY", "SELL")
            ]

    subset = pool[:top_council]
    evaluated: list[dict] = []
    approved: list[dict] = []
    rejected: list[dict] = []

    for c in subset:
        if str(c.get("signal", "HOLD")).upper() not in ("BUY", "SELL"):
            continue
        ev = evaluate_candidate(state, c, s)
        evaluated.append(ev)
        if ev["council"]["approved"]:
            approved.append(ev)
        else:
            meta = ev["council"].get("meta") or {}
            rejected.append({
                "symbol": c["symbol"],
                "signal": c.get("signal"),
                "meta_score": ev["council"].get("meta_score"),
                "reason": meta.get("rejection_reason") or "council rejected",
                "vetoes": meta.get("vetoes") or [],
            })

    report = {
        "council_mode": getattr(s, "council_mode", "shadow"),
        "scanned_symbols_count": len(state.get("symbols_analyzed") or []),
        "preliminary_ranked_count": len(ranked),
        "deep_analysis_top_n": top_deep,
        "council_evaluated_count": len(evaluated),
        "top_candidates": ranked[:10],
        "evaluated": evaluated,
        "approved": approved,
        "rejected": rejected,
        "approved_count": len(approved),
    }
    memory.store("council_last_report", report, ttl_seconds=86400 * 3)
    return report


# Backward-compatible alias for scalp_engine
def evaluate_batch(state: dict, candidates: list[dict], settings=None) -> dict[str, Any]:
    s = settings or get_settings()
    if not getattr(s, "council_enabled", True):
        approved = [c for c in candidates if float(c.get("strength") or 0) >= s.scalping_min_strength]
        return {"council_enabled": False, "evaluated": candidates, "approved": approved, "rejected": []}

    evaluated, approved, rejected = [], [], []
    top_n = int(getattr(s, "council_top_n", None) or getattr(s, "council_top_candidates", 8))
    for c in candidates[:top_n]:
        ev = evaluate_candidate(state, c, s)
        evaluated.append(ev)
        if ev["council"]["approved"]:
            approved.append(ev)
        else:
            rejected.append({"symbol": c["symbol"], "reason": "council rejected"})
    return {
        "council_enabled": True,
        "evaluated": evaluated,
        "approved": approved,
        "rejected": rejected,
    }
