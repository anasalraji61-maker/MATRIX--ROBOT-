"""
Supervisor Agent — the final decision-maker.
Synthesises all upstream agent outputs into one authoritative decision.
Uses LLM when available for nuanced reasoning; otherwise applies structured logic.
"""
from datetime import datetime, timezone
from config import get_settings
from models.schemas import SupervisorDecision


async def run(state: dict) -> dict:
    settings = get_settings()
    # Honor the mode that was set on the cycle's initial state (effective mode
    # from /mode override). Fall back to config default only if missing.
    mode = state.get("mode") or settings.trading_state
    risk = state.get("risk", {})
    best = state.get("best_analysis", {})
    sentiment = state.get("sentiment", {})

    if mode == "FROZEN":
        decision = SupervisorDecision(
            action="HOLD",
            symbol=best.get("symbol", "N/A"),
            confidence=0.0,
            reasoning="System is in FROZEN mode — all trading suspended",
            risk_note="No trades permitted",
        )
        return {**state, "decision": decision.model_dump(), "mode": mode}

    if not risk.get("approved", False):
        decision = SupervisorDecision(
            action="HOLD",
            symbol=best.get("symbol", "N/A"),
            confidence=0.0,
            reasoning=f"Risk agent rejected: {risk.get('reason', 'Unknown')}",
            risk_note=f"DD: {risk.get('current_daily_drawdown_pct',0):.2f}% / {risk.get('current_total_drawdown_pct',0):.2f}%",
        )
        return {**state, "decision": decision.model_dump(), "mode": mode}

    signal = best.get("signal", "HOLD")
    symbol = best.get("symbol", "")
    strength = best.get("strength", 0.0)
    analyses = state.get("analyses", [])

    # Count confirming signals across all symbols
    buy_count = sum(1 for a in analyses if a["signal"] == "BUY")
    sell_count = sum(1 for a in analyses if a["signal"] == "SELL")

    if settings.has_llm:
        decision = await _llm_decide(state, settings, mode)
    else:
        decision = _rule_decide(signal, symbol, strength, sentiment,
                                risk, buy_count, sell_count, mode)

    return {**state, "decision": decision.model_dump(), "mode": mode}


async def _llm_decide(state: dict, settings, mode: str) -> SupervisorDecision:
    try:
        from langchain_openai import ChatOpenAI
        from langchain_core.messages import SystemMessage, HumanMessage

        best = state.get("best_analysis", {})
        risk = state.get("risk", {})
        sentiment = state.get("sentiment", {})
        analyses_summary = "; ".join(
            f"{a['symbol']}: {a['signal']} ({a['strength']:.2f})"
            for a in state.get("analyses", [])
        )

        if settings.effective_openrouter_key:
            llm = ChatOpenAI(
                model="openai/gpt-4o-mini",
                openai_api_key=settings.effective_openrouter_key,
                openai_api_base="https://openrouter.ai/api/v1",
                temperature=0.05,
                max_tokens=300,
            )
        else:
            llm = ChatOpenAI(
                model="gpt-4o-mini",
                openai_api_key=settings.effective_openai_key,
                temperature=0.05,
                max_tokens=300,
            )

        system = (
            "You are the Supervisor of a small hedge fund's autonomous trading system. "
            "Your job is to make the final, definitive trade decision based on all agents' inputs. "
            "Be conservative. Protect capital first. "
            "Output JSON: {action: BUY|SELL|HOLD, symbol, confidence: 0.0-1.0, reasoning: str, risk_note: str}"
        )

        human = (
            f"Mode: {mode}\n"
            f"Best signal: {best.get('symbol')} {best.get('signal')} (strength={best.get('strength'):.2f})\n"
            f"All signals: {analyses_summary}\n"
            f"Sentiment: {sentiment.get('label')} (score={sentiment.get('score'):.2f})\n"
            f"Risk: approved={risk.get('approved')}, {risk.get('reason','')}\n"
            f"DD daily={risk.get('current_daily_drawdown_pct'):.2f}% total={risk.get('current_total_drawdown_pct'):.2f}%\n"
            "Make your final decision."
        )

        response = await llm.ainvoke([SystemMessage(content=system),
                                       HumanMessage(content=human)])

        import json, re
        m = re.search(r"\{.*\}", response.content, re.DOTALL)
        if m:
            data = json.loads(m.group())
            return SupervisorDecision(
                action=data.get("action", "HOLD").upper(),
                symbol=data.get("symbol", best.get("symbol", "")),
                confidence=float(data.get("confidence", 0.5)),
                reasoning=data.get("reasoning", "LLM decision"),
                risk_note=data.get("risk_note", ""),
            )
    except Exception:
        pass

    return _rule_decide(
        state.get("best_analysis", {}).get("signal", "HOLD"),
        state.get("best_analysis", {}).get("symbol", ""),
        state.get("best_analysis", {}).get("strength", 0.0),
        state.get("sentiment", {}),
        state.get("risk", {}),
        0, 0, mode,
    )


def _rule_decide(
    signal: str, symbol: str, strength: float,
    sentiment: dict, risk: dict,
    buy_count: int, sell_count: int, mode: str,
) -> SupervisorDecision:
    if signal == "HOLD":
        return SupervisorDecision(
            action="HOLD",
            symbol=symbol or "N/A",
            confidence=0.0,
            reasoning="No high-conviction signal across monitored pairs",
            risk_note="Standing aside preserves capital",
        )

    # Require sentiment alignment for higher confidence
    sent_label = sentiment.get("label", "NEUTRAL")
    aligned = (signal == "BUY" and sent_label == "POSITIVE") or \
              (signal == "SELL" and sent_label == "NEGATIVE")
    confidence = strength * (1.1 if aligned else 0.9)
    confidence = round(min(confidence, 0.98), 3)

    dd_note = (
        f"Daily DD={risk.get('current_daily_drawdown_pct',0):.2f}% "
        f"Total DD={risk.get('current_total_drawdown_pct',0):.2f}%"
    )

    return SupervisorDecision(
        action=signal,
        symbol=symbol,
        confidence=confidence,
        reasoning=(
            f"{signal} on {symbol} — strength={strength:.2f}, "
            f"sentiment={'aligned' if aligned else 'neutral'}, "
            f"confirming pairs={buy_count if signal=='BUY' else sell_count}"
        ),
        risk_note=dd_note,
    )
