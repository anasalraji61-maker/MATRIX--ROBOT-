"""
LangGraph state machine — the orchestration backbone of Matrix Robot.

Pipeline (sequential, each node adds to state):
  data_fetch → sentiment → analysis → risk → supervisor → execution (conditional)

The graph compiles once at startup and is reused for every trading cycle.
"""
from typing import TypedDict
from langgraph.graph import StateGraph, END, START
from agents import (
    data_agent,
    sentiment_agent,
    analysis_agent,
    agentic_brain,
    risk_agent,
    supervisor_agent,
    execution_agent,
)
from tools import emergency_guard


class TradingState(TypedDict, total=False):
    cycle_id: str
    started_at: str
    mode: str
    market_data: dict
    indicators: dict
    indicators_summaries: dict
    symbols_analyzed: list
    sentiment: dict
    analyses: list
    best_analysis: dict
    risk: dict
    decision: dict
    execution: dict
    executions: list
    errors: list
    # Advanced analytics layer
    mtf: dict
    mtf_summaries: dict
    ict: dict
    ict_summaries: dict
    volatility_regimes: dict
    correlation_report: dict
    economic_calendar: dict
    # FundedNext / prop-firm compliance layer
    account: dict
    prop_status: dict


# LangGraph requires async node functions defined at module level

async def _node_emergency(state: TradingState) -> TradingState:
    """FIRST node every cycle. Checks daily-DD lockout + emergency liquidation
    BEFORE any analysis runs. If locked, short-circuits the entire cycle."""
    try:
        guard = await emergency_guard.evaluate(dict(state))
        new_state = {**dict(state), "emergency": guard}
        if guard.get("locked"):
            new_state["execution"] = {
                "executed": False,
                "mode": state.get("mode", "PAPER_MODE"),
                "message": f"Daily lockout active: {guard.get('lockout', {}).get('reason', 'breached')}",
            }
        return new_state
    except Exception as e:
        return {**dict(state), "errors": list(state.get("errors", [])) + [f"emergency_guard: {e}"]}


async def _node_data(state: TradingState) -> TradingState:
    try:
        return await data_agent.run(dict(state))
    except Exception as e:
        return {**dict(state), "errors": list(state.get("errors", [])) + [f"data_agent: {e}"]}


async def _node_sentiment(state: TradingState) -> TradingState:
    try:
        return await sentiment_agent.run(dict(state))
    except Exception as e:
        return {**dict(state), "errors": list(state.get("errors", [])) + [f"sentiment_agent: {e}"]}


async def _node_analysis(state: TradingState) -> TradingState:
    """Agentic brain — LLM with tool-calling. Falls back to legacy
    ensemble analysis_agent internally on any failure or missing LLM key."""
    try:
        return await agentic_brain.run(dict(state))
    except Exception as e:
        return {**dict(state), "errors": list(state.get("errors", [])) + [f"agentic_brain: {e}"]}


async def _node_risk(state: TradingState) -> TradingState:
    try:
        return await risk_agent.run(dict(state))
    except Exception as e:
        return {**dict(state), "errors": list(state.get("errors", [])) + [f"risk_agent: {e}"]}


async def _node_supervisor(state: TradingState) -> TradingState:
    try:
        return await supervisor_agent.run(dict(state))
    except Exception as e:
        return {**dict(state), "errors": list(state.get("errors", [])) + [f"supervisor_agent: {e}"]}


async def _node_execution(state: TradingState) -> TradingState:
    try:
        return await execution_agent.run(dict(state))
    except Exception as e:
        return {**dict(state), "errors": list(state.get("errors", [])) + [f"execution_agent: {e}"]}


async def _node_skip(state: TradingState) -> TradingState:
    from datetime import datetime
    existing = state.get("decision") or {}
    emergency = state.get("emergency") or {}
    if emergency.get("locked"):
        lock = emergency.get("lockout", {}) or {}
        reason = lock.get("reason", "Daily DD lockout")
        message = f"DAILY LOCKOUT — {reason}. Resumes at UTC midnight."
        risk_note = f"Auto-liquidated; trading halted until UTC midnight ({reason})"
    else:
        message = "Supervisor decided to hold — no execution"
        risk_note = existing.get("risk_note") or "no execution"
    decision = {
        "action": existing.get("action", "HOLD"),
        "symbol": existing.get("symbol", "-"),
        "confidence": float(existing.get("confidence", 0.0)),
        "reasoning": existing.get("reasoning", message),
        "risk_note": risk_note,
        "timestamp": existing.get("timestamp", datetime.utcnow().isoformat()),
    }
    return {
        **dict(state),
        "decision": decision,
        "execution": {
            "executed": False,
            "mode": state.get("mode", "PAPER_MODE"),
            "message": message,
        },
    }


def _should_execute(state: TradingState) -> str:
    decision = state.get("decision", {})
    action = decision.get("action", "HOLD")
    risk_approved = state.get("risk", {}).get("approved", False)
    mode = state.get("mode", "PAPER_MODE")

    if action in ("BUY", "SELL") and risk_approved and mode != "FROZEN":
        return "execute"
    return "skip"


def build_graph():
    workflow = StateGraph(TradingState)

    workflow.add_node("emergency",  _node_emergency)
    workflow.add_node("data_fetch", _node_data)
    workflow.add_node("sentiment",  _node_sentiment)
    workflow.add_node("analysis",   _node_analysis)
    workflow.add_node("risk",       _node_risk)
    workflow.add_node("supervisor", _node_supervisor)
    workflow.add_node("execution",  _node_execution)
    workflow.add_node("skip",       _node_skip)

    workflow.add_edge(START, "emergency")
    workflow.add_conditional_edges(
        "emergency",
        lambda s: "locked" if (s.get("emergency") or {}).get("locked") else "continue",
        {"locked": "skip", "continue": "data_fetch"},
    )
    workflow.add_edge("data_fetch", "sentiment")
    workflow.add_edge("sentiment", "analysis")
    workflow.add_edge("analysis", "risk")
    workflow.add_edge("risk", "supervisor")
    workflow.add_conditional_edges(
        "supervisor",
        _should_execute,
        {"execute": "execution", "skip": "skip"},
    )
    workflow.add_edge("execution", END)
    workflow.add_edge("skip", END)

    return workflow.compile()


_compiled_graph = None


def get_graph():
    global _compiled_graph
    if _compiled_graph is None:
        _compiled_graph = build_graph()
    return _compiled_graph
