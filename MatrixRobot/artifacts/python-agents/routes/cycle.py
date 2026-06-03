import uuid
import asyncio
from datetime import datetime, timezone
from fastapi import APIRouter, BackgroundTasks, HTTPException
from pydantic import BaseModel
from config import get_settings
from agents.graph import get_graph
from models.schemas import CycleResult
from tools import memory

router = APIRouter()

# In-memory current cycle tracker (also stored in Redis when available)
_current_cycle: dict | None = None
_cycle_lock = asyncio.Lock()


class CycleRequest(BaseModel):
    dry_run: bool = False  # True = force PAPER_MODE regardless of settings


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
    settings = get_settings()
    started = datetime.now(timezone.utc)
    mode = "PAPER_MODE" if dry_run else get_effective_mode()

    try:
        graph = get_graph()
        initial_state = {
            "cycle_id": cycle_id,
            "started_at": started.isoformat(),
            "mode": mode,
            "errors": [],
        }

        final_state = await graph.ainvoke(initial_state)

        finished = datetime.now(timezone.utc)
        duration_ms = int((finished - started).total_seconds() * 1000)

        decision = final_state.get("decision", {})
        execution = final_state.get("execution", {})

        result = {
            "cycle_id": cycle_id,
            "started_at": started.isoformat(),
            "finished_at": finished.isoformat(),
            "status": "completed",
            "mode": mode,
            "symbols_analyzed": final_state.get("symbols_analyzed", []),
            "decision": decision,
            "execution": execution,
            "errors": final_state.get("errors", []),
            "duration_ms": duration_ms,
            # Agentic brain output (one analysis per symbol it reviewed)
            "analyses": final_state.get("analyses", []),
            # Advanced analytics snapshot (used by /agents/analytics)
            "indicators": final_state.get("indicators", {}),
            "mtf": final_state.get("mtf", {}),
            "ict": final_state.get("ict", {}),
            "ict_summaries": final_state.get("ict_summaries", {}),
            "volatility_regimes": final_state.get("volatility_regimes", {}),
            "correlation_report": final_state.get("correlation_report"),
            "economic_calendar": final_state.get("economic_calendar"),
            # FundedNext compliance snapshot
            "risk": final_state.get("risk"),
            "prop_status": final_state.get("prop_status"),
            "account": final_state.get("account"),
        }

        memory.store_cycle_result(result)

        # Update agent state
        risk = final_state.get("risk", {})
        state_update = {
            "mode": mode,
            "last_cycle_id": cycle_id,
            "last_cycle_at": finished.isoformat(),
            "last_decision": decision.get("action", "HOLD"),
            "daily_drawdown_pct": risk.get("current_daily_drawdown_pct", 0.0),
            "total_drawdown_pct": risk.get("current_total_drawdown_pct", 0.0),
            "is_ready": True,
        }
        memory.store_state(state_update)

        # Persistent DD audit trail for FN compliance review
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

        async with _cycle_lock:
            _current_cycle = result

    except Exception as e:
        finished = datetime.now(timezone.utc)
        result = {
            "cycle_id": cycle_id,
            "started_at": started.isoformat(),
            "finished_at": finished.isoformat(),
            "status": "failed",
            "mode": mode,
            "symbols_analyzed": [],
            "decision": None,
            "execution": None,
            "errors": [str(e)],
            "duration_ms": int((finished - started).total_seconds() * 1000),
        }
        memory.store_cycle_result(result)
        async with _cycle_lock:
            _current_cycle = result
