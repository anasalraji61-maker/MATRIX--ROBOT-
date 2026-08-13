import uuid
import asyncio
import logging
from datetime import datetime, timezone
from fastapi import APIRouter, BackgroundTasks, HTTPException
from pydantic import BaseModel
from config import get_settings
from agents.graph import get_graph
from models.schemas import CycleResult
from tools import memory

router = APIRouter()
logger = logging.getLogger("matrix.cycle")

_current_cycle: dict | None = None
_cycle_lock = asyncio.Lock()


class CycleRequest(BaseModel):
    dry_run: bool = False


@router.post("/cycle/run", response_model=CycleResult)
async def run_cycle(req: CycleRequest, background_tasks: BackgroundTasks):
    global _current_cycle

    async with _cycle_lock:
        if _current_cycle and _current_cycle.get("status") == "running":
            raise HTTPException(
                status_code=409,
                detail=f"Cycle {_current_cycle['cycle_id']} already running",
            )
        cycle_id = str(uuid.uuid4())[:8]
        _current_cycle = {
            "cycle_id": cycle_id,
            "started_at": datetime.now(timezone.utc).isoformat(),
            "status": "running",
        }

    from routes.trading import get_effective_mode
    background_tasks.add_task(_execute_cycle, cycle_id, req.dry_run)

    return CycleResult(
        cycle_id=cycle_id,
        started_at=_current_cycle["started_at"],
        status="running",
        mode=get_effective_mode(),
    )


@router.get("/cycle/status", response_model=CycleResult)
async def cycle_status():
    cached = memory.get_last_cycle()
    if cached:
        return CycleResult(**cached)
    if _current_cycle:
        return CycleResult(**_current_cycle)
    raise HTTPException(status_code=404, detail="No cycles have run yet")


async def _execute_cycle(cycle_id: str, dry_run: bool):
    global _current_cycle
    from routes.trading import get_effective_mode
    from tools.cycle_planner import plan_cycle

    settings = get_settings()
    started = datetime.now(timezone.utc)
    mode = "PAPER_MODE" if dry_run else get_effective_mode()
    cycle_plan = plan_cycle(mode, settings)
    logger.info(
        "Cycle %s plan: type=%s brain=%s kz=%s interval=%smin next_full=%s",
        cycle_id,
        cycle_plan.get("cycle_type", "full"),
        cycle_plan.get("brain_active", False),
        cycle_plan.get("active_killzone", "none"),
        cycle_plan.get("scheduler_interval_minutes"),
        cycle_plan.get("next_full_cycle_at"),
    )

    try:
        cycle_type = cycle_plan.get("cycle_type", "full")
        if cycle_type == "maintenance":
            await _execute_maintenance_cycle(cycle_id, mode, started, cycle_plan)
            return
        if cycle_type == "scanner":
            await _execute_scanner_cycle(cycle_id, mode, started, cycle_plan)
            return
        await _execute_full_cycle(cycle_id, mode, started, cycle_plan)
    except Exception as e:
        finished = datetime.now(timezone.utc)
        result = {
            "cycle_id": cycle_id,
            "started_at": started.isoformat(),
            "finished_at": finished.isoformat(),
            "status": "failed",
            "mode": mode,
            "cycle_type": cycle_plan.get("cycle_type", "full"),
            "brain_active": cycle_plan.get("brain_active", False),
            "symbols_analyzed": [],
            "decision": None,
            "execution": None,
            "errors": [str(e)],
            "duration_ms": int((finished - started).total_seconds() * 1000),
        }
        memory.store_cycle_result(result)
        async with _cycle_lock:
            _current_cycle = result
        try:
            from tools import telegram_alerts
            if get_settings().has_telegram:
                await telegram_alerts.send(f"Cycle {cycle_id} FAILED: {e}", level="error")
        except Exception:
            pass


async def _execute_full_cycle(cycle_id: str, mode: str, started: datetime, cycle_plan: dict):
    global _current_cycle
    from tools.cycle_planner import record_cycle_type

    from tools import circuit_status
    preflight = await circuit_status.preflight_cycle(mode)
    if not preflight.get("can_run"):
        finished = datetime.now(timezone.utc)
        reason = preflight.get("reason", "blocked")
        message = preflight.get("message", "Cycle blocked")
        result = {
            "cycle_id": cycle_id,
            "started_at": started.isoformat(),
            "finished_at": finished.isoformat(),
            "status": "skipped",
            "mode": mode,
            "cycle_type": "full",
            "brain_active": True,
            "cycle_plan": cycle_plan,
            "symbols_analyzed": [],
            "decision": {
                "action": "HOLD",
                "symbol": "N/A",
                "confidence": 0.0,
                "reasoning": message,
                "risk_note": reason,
                "approved_trades": [],
            },
            "execution": {"executed": False, "mode": mode, "message": message},
            "errors": [],
            "duration_ms": int((finished - started).total_seconds() * 1000),
            "preflight": preflight,
        }
        memory.store_cycle_result(result)
        async with _cycle_lock:
            _current_cycle = result
        try:
            from tools import telegram_alerts
            if get_settings().has_telegram and reason in (
                "bridge_circuit_open", "bridge_unreachable", "bridge_stale", "daily_lockout",
            ):
                await telegram_alerts.alert_cycle_skipped(cycle_id, reason, message)
        except Exception:
            pass
        logger.warning("Cycle %s skipped: %s — %s", cycle_id, reason, message)
        return

    graph = get_graph()
    initial_state = {
        "cycle_id": cycle_id,
        "started_at": started.isoformat(),
        "mode": mode,
        "cycle_plan": cycle_plan,
        "errors": [],
    }
    final_state = await graph.ainvoke(initial_state)

    finished = datetime.now(timezone.utc)
    duration_ms = int((finished - started).total_seconds() * 1000)
    watcher_stats = record_cycle_type("full")

    result = _build_cycle_result(
        cycle_id, started, finished, mode, duration_ms, final_state,
        cycle_type="full",
        brain_active=True,
        cycle_plan={**cycle_plan, "watcher_stats": watcher_stats},
    )
    try:
        from tools import self_learning
        sl_report = self_learning.ingest_cycle(final_state, cycle_id=cycle_id)
        result["self_learning"] = sl_report
        final_state = {**final_state, "self_learning": sl_report}
    except Exception as e:
        logger.debug("self_learning ingest skipped: %s", e)
    memory.store_cycle_result(result)
    _persist_cycle_state(mode, cycle_id, finished, final_state.get("decision", {}), final_state)
    await _run_scalp_if_enabled(final_state, mode)
    async with _cycle_lock:
        _current_cycle = result
    await _telegram_after_cycle(cycle_id, mode, final_state, duration_ms)


async def _execute_maintenance_cycle(cycle_id: str, mode: str, started: datetime, cycle_plan: dict):
    global _current_cycle
    from tools.cycle_planner import record_cycle_type
    from agents import position_manager_agent
    from tools import account_state, circuit_status, emergency_guard

    state: dict = {
        "cycle_id": cycle_id,
        "started_at": started.isoformat(),
        "mode": mode,
        "cycle_plan": cycle_plan,
        "errors": [],
    }
    guard = await emergency_guard.evaluate(state)
    state["emergency"] = guard
    if guard.get("locked"):
        finished = datetime.now(timezone.utc)
        message = f"Maintenance — lockout: {guard.get('lockout', {}).get('reason', 'locked')}"
        result = _light_cycle_result(cycle_id, started, finished, mode, cycle_plan, state, message=message)
        memory.store_cycle_result(result)
        async with _cycle_lock:
            _current_cycle = result
        return

    state = await position_manager_agent.run(state)
    try:
        await account_state.refresh_account()
        if mode == "ACTIVE":
            await account_state.sync_open_positions()
    except Exception as e:
        state["errors"] = list(state.get("errors", [])) + [f"account_sync: {e}"]

    state["circuit_status"] = await circuit_status.full_report()

    finished = datetime.now(timezone.utc)
    duration_ms = int((finished - started).total_seconds() * 1000)
    pm = state.get("position_management") or {}
    open_n = cycle_plan.get("open_positions", 0)
    message = (
        f"Maintenance — {open_n} open position(s), "
        f"{len(pm.get('actions') or [])} management action(s)"
    )
    watcher_stats = record_cycle_type("maintenance")
    result = _light_cycle_result(
        cycle_id, started, finished, mode, cycle_plan, state,
        message=message, duration_ms=duration_ms, watcher_stats=watcher_stats,
    )
    memory.store_cycle_result(result)
    async with _cycle_lock:
        _current_cycle = result
    await _telegram_light(cycle_plan, open_n, message)


async def _execute_scanner_cycle(cycle_id: str, mode: str, started: datetime, cycle_plan: dict):
    global _current_cycle
    from tools.cycle_planner import record_cycle_type
    from agents import (
        data_agent, sentiment_agent, position_manager_agent,
        risk_agent, supervisor_agent,
    )
    from tools import emergency_guard
    from tools.off_session_scanner import run_scan
    from tools.off_session_limits import scanner_may_execute_off_session_small

    settings = get_settings()
    state: dict = {
        "cycle_id": cycle_id,
        "started_at": started.isoformat(),
        "mode": mode,
        "cycle_plan": cycle_plan,
        "errors": [],
    }
    guard = await emergency_guard.evaluate(state)
    state["emergency"] = guard
    if guard.get("locked"):
        finished = datetime.now(timezone.utc)
        result = _light_cycle_result(
            cycle_id, started, finished, mode, cycle_plan, state,
            message="Scanner skipped — emergency lockout active",
        )
        memory.store_cycle_result(result)
        async with _cycle_lock:
            _current_cycle = result
        return

    state = await position_manager_agent.run(state)
    state = await data_agent.run(state)
    state = await sentiment_agent.run(state)

    scan = await run_scan(state, escalate=True)
    state = {**state, **scan}

    state = await risk_agent.run(state)
    state = await supervisor_agent.run(state)

    candidates = scan.get("off_session_candidates") or []
    escalated = scan.get("off_session_escalated_to_brain") or []
    may_execute = scanner_may_execute_off_session_small(mode, cycle_plan, settings)
    risk_approved = bool((state.get("risk") or {}).get("approved"))
    approved_trades = state.get("approved_risk_trades") or []

    if may_execute and risk_approved and approved_trades:
        from agents import execution_agent
        state = await execution_agent.run(state)
        decision = state.get("decision") or {}
        execution = state.get("execution") or {}
        filled = sum(1 for e in (state.get("executions") or []) if e.get("executed"))
        if execution.get("executed") or filled:
            reasoning = (
                f"Off-session scanner — executed {filled} SMALL trade(s) "
                f"({len(approved_trades)} risk-approved)"
            )
        else:
            reasoning = (
                f"Off-session scanner — {len(candidates)} candidate(s), "
                f"{len(escalated)} LLM escalated; execution attempted, not filled"
            )
    else:
        if candidates:
            suffix = (
                "; execution disabled (SMART_WATCHER_EXECUTE_OFF_SESSION_SMALL=false)"
                if not may_execute
                else "; no risk-approved SMALL trades"
            )
            reasoning = (
                f"Off-session scanner — {len(candidates)} candidate(s), "
                f"{len(escalated)} LLM escalated{suffix}"
            )
        else:
            reasoning = "Off-session scanner — no strong setups"

        decision = {
            **(state.get("decision") or {}),
            "action": "HOLD",
            "reasoning": reasoning,
            "approved_trades": [],
        }
        execution = {
            "executed": False,
            "mode": mode,
            "message": (
                "Outside killzone — candidates logged only"
                if not may_execute
                else "Outside killzone — no risk-approved SMALL trades"
            ),
        }
        state["decision"] = decision
        state["execution"] = execution

    finished = datetime.now(timezone.utc)
    duration_ms = int((finished - started).total_seconds() * 1000)
    watcher_stats = record_cycle_type("scanner", escalated=len(escalated))

    result = _build_cycle_result(
        cycle_id, started, finished, mode, duration_ms, state,
        cycle_type="scanner",
        brain_active=False,
        cycle_plan={**cycle_plan, "watcher_stats": watcher_stats},
        decision=decision,
        execution=execution,
    )
    result["off_session_scanned_symbols"] = scan.get("off_session_scanned_symbols", [])
    result["off_session_candidates"] = candidates
    result["off_session_escalated_to_brain"] = escalated
    result["off_session_scan_rejected"] = scan.get("off_session_scan_rejected", {})
    result["off_session_execution_enabled"] = may_execute

    memory.store_cycle_result(result)
    _persist_cycle_state(mode, cycle_id, finished, decision, state)
    await _run_scalp_if_enabled(state, mode)
    async with _cycle_lock:
        _current_cycle = result
    if execution.get("executed"):
        await _telegram_after_cycle(cycle_id, mode, state, duration_ms)
    else:
        await _telegram_light(cycle_plan, cycle_plan.get("open_positions", 0), reasoning, candidates, escalated)


def _build_cycle_result(
    cycle_id, started, finished, mode, duration_ms, final_state,
    *, cycle_type, brain_active, cycle_plan,
    decision=None, execution=None,
) -> dict:
    decision = decision or final_state.get("decision", {})
    execution = execution or final_state.get("execution", {})
    return {
        "cycle_id": cycle_id,
        "started_at": started.isoformat(),
        "finished_at": finished.isoformat(),
        "status": "completed",
        "mode": mode,
        "cycle_type": cycle_type,
        "brain_active": brain_active,
        "cycle_plan": cycle_plan,
        "next_full_cycle_at": cycle_plan.get("next_full_cycle_at"),
        "symbols_analyzed": final_state.get("symbols_analyzed", []),
        "decision": decision,
        "execution": execution,
        "errors": final_state.get("errors", []),
        "duration_ms": duration_ms,
        "analyses": final_state.get("analyses", []),
        "indicators": final_state.get("indicators", {}),
        "mtf": final_state.get("mtf", {}),
        "ict": final_state.get("ict", {}),
        "ict_summaries": final_state.get("ict_summaries", {}),
        "volatility_regimes": final_state.get("volatility_regimes", {}),
        "correlation_report": final_state.get("correlation_report"),
        "economic_calendar": final_state.get("economic_calendar"),
        "risk": final_state.get("risk"),
        "prop_status": final_state.get("prop_status"),
        "account": final_state.get("account"),
        "sentiment": final_state.get("sentiment"),
        "session_profile": final_state.get("session_profile"),
        "position_management": final_state.get("position_management"),
        "data_quarantine": final_state.get("data_quarantine"),
        "risk_rejection_report": final_state.get("risk_rejection_report"),
        "council_report": final_state.get("council_report"),
    }


def _light_cycle_result(
    cycle_id, started, finished, mode, cycle_plan, state,
    *, message: str, duration_ms: int | None = None,
    watcher_stats: dict | None = None,
) -> dict:
    if duration_ms is None:
        duration_ms = int((finished - started).total_seconds() * 1000)
    plan = {**cycle_plan}
    if watcher_stats:
        plan["watcher_stats"] = watcher_stats
    return {
        "cycle_id": cycle_id,
        "started_at": started.isoformat(),
        "finished_at": finished.isoformat(),
        "status": "completed",
        "mode": mode,
        "cycle_type": cycle_plan.get("cycle_type", "maintenance"),
        "brain_active": False,
        "cycle_plan": plan,
        "next_full_cycle_at": cycle_plan.get("next_full_cycle_at"),
        "symbols_analyzed": [],
        "decision": {
            "action": "HOLD",
            "symbol": "N/A",
            "confidence": 0.0,
            "reasoning": message,
            "risk_note": str(cycle_plan.get("active_killzone", "none")),
            "approved_trades": [],
        },
        "execution": {"executed": False, "mode": mode, "message": message},
        "errors": state.get("errors", []),
        "duration_ms": duration_ms,
        "position_management": state.get("position_management"),
        "circuit_status": state.get("circuit_status"),
    }


def _persist_cycle_state(mode, cycle_id, finished, decision, final_state):
    risk = final_state.get("risk", {})
    memory.store_state({
        "mode": mode,
        "last_cycle_id": cycle_id,
        "last_cycle_at": finished.isoformat(),
        "last_decision": decision.get("action", "HOLD"),
        "daily_drawdown_pct": risk.get("current_daily_drawdown_pct", 0.0),
        "total_drawdown_pct": risk.get("current_total_drawdown_pct", 0.0),
        "is_ready": True,
    })
    try:
        account = final_state.get("account") or {}
        prop = final_state.get("prop_status") or {}
        memory.log_drawdown_snapshot({
            "balance": account.get("balance"),
            "equity": account.get("equity"),
            "daily_dd_pct": risk.get("current_daily_drawdown_pct"),
            "total_dd_pct": risk.get("current_total_drawdown_pct"),
            "open_positions": len(final_state.get("positions", []) or []),
            "open_risk_pct": prop.get("open_risk_pct"),
            "margin_used_pct": prop.get("margin_used_pct"),
        })
    except Exception:
        pass


async def _run_scalp_if_enabled(state: dict, mode: str) -> None:
    try:
        from tools.scalp_engine import run_scalp_pipeline
        state["mode"] = mode
        report = await run_scalp_pipeline(state)
        state["scalp_report"] = report
    except Exception as e:
        logger.warning("V11 scalp pipeline failed: %s", e)


async def _telegram_after_cycle(cycle_id, mode, final_state, duration_ms):
    try:
        from tools import telegram_alerts
        if get_settings().has_telegram:
            await telegram_alerts.alert_cycle_summary(
                cycle_id=cycle_id,
                mode=mode,
                decision=final_state.get("decision"),
                sentiment=final_state.get("sentiment"),
                execution=final_state.get("execution"),
                duration_ms=duration_ms,
                errors=final_state.get("errors"),
            )
    except Exception:
        pass


async def _telegram_light(cycle_plan, open_n, message, candidates=None, escalated=None):
    try:
        from tools import telegram_alerts
        if not get_settings().has_telegram:
            return
        lines = [
            f"Outside session — {cycle_plan.get('cycle_type', 'light')}",
            message,
        ]
        if candidates:
            top = ", ".join(
                f"{c['symbol']} {c['signal']} {c['strength']:.2f}" for c in candidates[:3]
            )
            lines.append(f"Candidates: {top}")
        if escalated:
            lines.append(f"LLM escalated: {', '.join(escalated)}")
        if open_n:
            lines.append(f"Open positions: {open_n}")
        else:
            lines.append(
                f"Next full: {cycle_plan.get('next_killzone')} @ {cycle_plan.get('next_full_cycle_at')}"
            )
        saved = (cycle_plan.get("watcher_stats") or {}).get("estimated_cost_saved_usd", 0)
        if saved:
            lines.append(f"Est. saved today: ${saved:.2f}")
        await telegram_alerts.send("\n".join(lines), level="info", disable_notification=True)
    except Exception:
        pass
