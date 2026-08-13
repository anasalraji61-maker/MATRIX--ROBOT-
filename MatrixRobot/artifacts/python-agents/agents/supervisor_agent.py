"""
Supervisor Agent — the final decision-maker.
Synthesises all upstream agent outputs into one authoritative decision.

Phase 1.1: `approved_trades` is the single source of truth for Execution.
Dashboard fields (action/symbol/confidence) mirror the top approved trade.
"""
import logging

from config import get_settings
from models.schemas import SupervisorDecision, ApprovedTrade
from tools import trade_tiers

logger = logging.getLogger("matrix.supervisor")


def _finalize_approved(analyses: list[dict], state: dict, settings) -> list[ApprovedTrade]:
    approved = build_from_risk_approved(state, settings)
    if not approved:
        return approved
    from tools import ml_filter, rl_filter, self_learning
    approved, sl_removed = self_learning.filter_approved_trades(approved, settings)
    if sl_removed:
        state["self_learning_supervisor_removed"] = sl_removed
    filtered, ml_scores = ml_filter.filter_trades(approved, state, settings)
    if ml_scores:
        state["ml_scores"] = ml_scores
    filtered, rl_scores = rl_filter.filter_trades(filtered, state, settings)
    if rl_scores:
        state["rl_scores"] = rl_scores
    return filtered


def build_approved_trades(analyses: list[dict], settings=None) -> list[ApprovedTrade]:
    """Rank actionable brain signals; cap at max concurrent slots."""
    s = settings or get_settings()
    min_strength = trade_tiers.min_candidate_strength(s)
    cap = int(s.max_concurrent_positions)

    ranked: list[ApprovedTrade] = []
    for a in analyses:
        signal = str(a.get("signal", "HOLD")).upper()
        strength = float(a.get("strength") or 0.0)
        symbol = str(a.get("symbol") or "").strip()
        if signal not in ("BUY", "SELL") or not symbol:
            continue
        if strength < min_strength:
            continue
        if trade_tiers.classify_trade_tier(strength, s) == "HOLD":
            continue
        ranked.append(ApprovedTrade(symbol=symbol, signal=signal, strength=strength))

    ranked.sort(key=lambda t: t.strength, reverse=True)
    return ranked[:cap]


def build_from_risk_approved(state: dict, settings=None) -> list[ApprovedTrade]:
    """Prefer risk-approved trades when Phase 6 batch sizing is present."""
    risk_trades = state.get("approved_risk_trades") or []
    if risk_trades:
        return [
            ApprovedTrade(
                symbol=str(t["symbol"]),
                signal=str(t["signal"]),
                strength=float(t.get("strength", 0.0)),
            )
            for t in risk_trades
            if t.get("approved")
        ]
    return build_approved_trades(state.get("analyses", []), settings)


def _hold_decision(
    symbol: str,
    reasoning: str,
    risk_note: str,
) -> SupervisorDecision:
    return SupervisorDecision(
        action="HOLD",
        symbol=symbol or "N/A",
        confidence=0.0,
        reasoning=reasoning,
        risk_note=risk_note,
        approved_trades=[],
    )


def _decision_from_approved(
    approved: list[ApprovedTrade],
    reasoning: str,
    risk_note: str,
) -> SupervisorDecision:
    if not approved:
        return _hold_decision("N/A", reasoning, risk_note)

    top = approved[0]
    summary = ", ".join(f"{t.symbol} {t.signal}" for t in approved)
    full_reasoning = (
        f"Approved {len(approved)} trade(s): {summary}. {reasoning}"
    ).strip()

    return SupervisorDecision(
        action=top.signal,
        symbol=top.symbol,
        confidence=round(min(top.strength, 0.98), 3),
        reasoning=full_reasoning,
        risk_note=risk_note,
        approved_trades=approved,
    )


def _rule_fallback_after_llm_veto(
    approved: list[ApprovedTrade],
    llm_reason: str,
    dd_note: str,
    settings,
) -> SupervisorDecision | None:
    """If LLM vetoes but Risk already cleared NORMAL-tier signals, approve via rules.

    Fixes over-conservative GPT supervisor vetoing e.g. US500 @ 0.80 while Risk
    approved the cycle. SMALL-tier signals still require LLM approval.
    """
    if not approved:
        return None
    floor = float(settings.normal_trade_min_strength)
    strong = [t for t in approved if t.strength >= floor]
    if not strong:
        return None
    short = (llm_reason or "conservative veto").strip()
    if len(short) > 140:
        short = short[:137] + "..."
    reasoning = (
        f"LLM veto overridden — rule fallback: {len(strong)} NORMAL-tier trade(s) "
        f"(strength >= {floor:.2f}) already passed Risk. LLM note: {short}"
    )
    return _decision_from_approved(strong, reasoning, dd_note)


async def run(state: dict) -> dict:
    settings = get_settings()
    mode = state.get("mode") or settings.trading_state
    risk = state.get("risk", {})
    best = state.get("best_analysis", {})
    sentiment = state.get("sentiment", {})
    analyses = state.get("analyses", [])

    if mode == "FROZEN":
        decision = _hold_decision(
            best.get("symbol", "N/A"),
            "System is in FROZEN mode — all trading suspended",
            "No trades permitted",
        )
        return {**state, "decision": decision.model_dump(), "mode": mode}

    if not risk.get("approved", False) and not state.get("approved_risk_trades"):
        decision = _hold_decision(
            best.get("symbol", "N/A"),
            f"Risk agent rejected: {risk.get('reason', 'Unknown')}",
            (
                f"DD: {risk.get('current_daily_drawdown_pct', 0):.2f}% / "
                f"{risk.get('current_total_drawdown_pct', 0):.2f}%"
            ),
        )
        return {**state, "decision": decision.model_dump(), "mode": mode}

    signal = best.get("signal", "HOLD")
    symbol = best.get("symbol", "")
    strength = best.get("strength", 0.0)
    buy_count = sum(1 for a in analyses if a.get("signal") == "BUY")
    sell_count = sum(1 for a in analyses if a.get("signal") == "SELL")
    dd_note = (
        f"Daily DD={risk.get('current_daily_drawdown_pct', 0):.2f}% "
        f"Total DD={risk.get('current_total_drawdown_pct', 0):.2f}%"
    )

    cycle_plan = state.get("cycle_plan") or {}
    brain_active = cycle_plan.get("brain_active", True)
    if settings.has_llm and brain_active:
        decision = await _llm_decide(
            state, settings, mode, dd_note, buy_count, sell_count,
        )
    else:
        decision = _rule_decide(
            signal, symbol, strength, sentiment, buy_count, sell_count, dd_note,
            analyses, settings, state,
        )

    return {**state, "decision": decision.model_dump(), "mode": mode}


async def _llm_decide(
    state: dict,
    settings,
    mode: str,
    dd_note: str,
    buy_count: int,
    sell_count: int,
) -> SupervisorDecision:
    best = state.get("best_analysis", {})
    risk = state.get("risk", {})
    sentiment = state.get("sentiment", {})
    analyses = state.get("analyses", [])
    approved = _finalize_approved(analyses, state, settings)

    def _pct(val) -> float:
        try:
            return float(val if val is not None else 0.0)
        except (TypeError, ValueError):
            return 0.0

    try:
        from langchain_openai import ChatOpenAI
        from langchain_core.messages import SystemMessage, HumanMessage

        analyses_summary = "; ".join(
            f"{a['symbol']}: {a['signal']} ({a['strength']:.2f})"
            for a in analyses
        )
        approved_summary = ", ".join(
            f"{t.symbol} {t.signal} ({t.strength:.2f})" for t in approved
        ) or "none"

        if settings.effective_openrouter_key:
            or_model = settings.primary_model or "openai/gpt-4o-mini"
            llm = ChatOpenAI(
                model=or_model,
                openai_api_key=settings.effective_openrouter_key,
                openai_api_base="https://openrouter.ai/api/v1",
                temperature=0.05,
                max_tokens=300,
            )
        else:
            fb = settings.fallback_model or "gpt-4o-mini"
            llm = ChatOpenAI(
                model=fb.split("/")[-1] if "/" in fb else fb,
                openai_api_key=settings.effective_openai_key,
                temperature=0.05,
                max_tokens=300,
            )

        system = (
            "You are the Supervisor of a small hedge fund's autonomous trading system. "
            "Your job is to approve or reject the proposed trade batch. "
            "Be conservative. Protect capital first. "
            "Output JSON: {action: BUY|SELL|HOLD, symbol, confidence: 0.0-1.0, "
            "reasoning: str, risk_note: str}. "
            "Use HOLD to veto the entire batch; BUY/SELL approves the proposed batch."
        )

        human = (
            f"Mode: {mode}\n"
            f"Best signal: {best.get('symbol')} {best.get('signal')} "
            f"(strength={best.get('strength'):.2f})\n"
            f"All signals: {analyses_summary}\n"
            f"Proposed approved batch ({len(approved)}): {approved_summary}\n"
            f"Sentiment: {sentiment.get('label')} (score={_pct(sentiment.get('score')):.2f})\n"
            f"Risk: approved={risk.get('approved')}, {risk.get('reason', '')}\n"
            f"DD daily={_pct(risk.get('current_daily_drawdown_pct')):.2f}% "
            f"total={_pct(risk.get('current_total_drawdown_pct')):.2f}%\n"
            "Approve the batch (action=BUY or SELL on top symbol) or veto with HOLD."
        )

        response = await llm.ainvoke([
            SystemMessage(content=system),
            HumanMessage(content=human),
        ])

        import json
        import re

        m = re.search(r"\{.*\}", response.content, re.DOTALL)
        if m:
            data = json.loads(m.group())
            action = str(data.get("action", "HOLD")).upper()
            if action in ("BUY", "SELL") and approved:
                return _decision_from_approved(
                    approved,
                    data.get("reasoning", "LLM approved batch"),
                    data.get("risk_note", dd_note),
                )
            fallback = _rule_fallback_after_llm_veto(
                approved,
                data.get("reasoning", "LLM veto — no execution"),
                data.get("risk_note", dd_note),
                settings,
            )
            if fallback:
                return fallback
            return _hold_decision(
                data.get("symbol", best.get("symbol", "N/A")),
                data.get("reasoning", "LLM veto — no execution"),
                data.get("risk_note", dd_note),
            )
    except Exception as exc:
        logger.warning("Supervisor LLM decision failed — rule fallback: %s", exc)
        from tools import memory
        memory.store("supervisor_llm_error", str(exc)[:500], ttl_seconds=3600)

    return _rule_decide(
        best.get("signal", "HOLD"),
        best.get("symbol", ""),
        best.get("strength", 0.0),
        sentiment,
        buy_count,
        sell_count,
        dd_note,
        analyses,
        settings,
        state,
    )


def _rule_decide(
    signal: str,
    symbol: str,
    strength: float,
    sentiment: dict,
    buy_count: int,
    sell_count: int,
    dd_note: str,
    analyses: list[dict],
    settings,
    state: dict,
) -> SupervisorDecision:
    approved = _finalize_approved(analyses, state, settings)
    if not approved:
        return _hold_decision(
            symbol or "N/A",
            "No high-conviction signal across monitored pairs",
            "Standing aside preserves capital",
        )

    top = approved[0]
    signal = top.signal
    symbol = top.symbol
    strength = top.strength

    sent_label = sentiment.get("label", "NEUTRAL")
    aligned = (signal == "BUY" and sent_label == "POSITIVE") or \
              (signal == "SELL" and sent_label == "NEGATIVE")
    confidence = strength * (1.1 if aligned else 0.9)
    confidence = round(min(confidence, 0.98), 3)

    reasoning = (
        f"{signal} on {symbol} — strength={strength:.2f}, "
        f"sentiment={'aligned' if aligned else 'neutral'}, "
        f"confirming pairs={buy_count if signal == 'BUY' else sell_count}"
    )

    decision = _decision_from_approved(approved, reasoning, dd_note)
    decision.confidence = confidence
    return decision
