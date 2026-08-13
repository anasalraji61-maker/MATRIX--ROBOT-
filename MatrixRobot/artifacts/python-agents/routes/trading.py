"""
Trading control routes — mode switching, scheduler, live positions.
"""
import asyncio
import logging
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from config import get_settings
from tools import memory, mt5_bridge
import runtime_state

logger = logging.getLogger("matrix.trading")
router = APIRouter()

# ── In-memory trading state overrides ─────────────────────────
# Initialized from persistent runtime_state on import so the
# user-set mode survives service restarts.
_mode_override: Optional[str] = runtime_state.get_mode()

# ── Scheduler state ────────────────────────────────────────────
_scheduler_task: Optional[asyncio.Task] = None
_scheduler_interval_minutes: int = 90
_scheduler_running = False
_scheduler_cycles_run = 0
_scheduler_last_run: Optional[str] = None


def get_effective_mode() -> str:
    if _mode_override is not None:
        return _mode_override
    return get_settings().trading_state


# ──────────────────────────────────────────────────────────────
# Mode switch
# ──────────────────────────────────────────────────────────────

class ModeRequest(BaseModel):
    mode: str  # PAPER_MODE | ACTIVE | FROZEN


@router.post("/mode")
async def set_mode(req: ModeRequest):
    global _mode_override
    valid = {"PAPER_MODE", "ACTIVE", "FROZEN"}
    if req.mode not in valid:
        raise HTTPException(400, f"Invalid mode. Must be one of: {valid}")

    if req.mode == "ACTIVE":
        settings = get_settings()
        # Hard gate: ALLOW_LIVE_TRADING env var must be explicitly set to true
        if not settings.allow_live_trading:
            raise HTTPException(403,
                "Live trading is disabled. Set ALLOW_LIVE_TRADING=true in Replit Secrets "
                "and restart the Python service to enable ACTIVE mode.")
        bridge_ok = bool(settings.mt5_bridge_url)
        native_ok = settings.has_mt5
        if not bridge_ok and not native_ok:
            raise HTTPException(400,
                "Cannot activate live trading: set MT5_BRIDGE_URL (remote bridge) "
                "or MT5_LOGIN + MT5_PASSWORD + MT5_SERVER (Windows)")

    old_mode = get_effective_mode()
    _mode_override = req.mode
    logger.info(f"Trading mode changed: {old_mode} → {req.mode}")

    # Persist across restarts
    runtime_state.set_mode(req.mode)

    # Update stored state
    cached = memory.get_state() or {}
    cached["mode"] = req.mode
    memory.store_state(cached)

    return {
        "success": True,
        "previous_mode": old_mode,
        "mode": req.mode,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


@router.get("/mode")
async def get_mode():
    settings = get_settings()
    return {
        "mode": get_effective_mode(),
        "override_active": _mode_override is not None,
        "config_mode": settings.trading_state,
        "mt5_bridge_configured": bool(settings.mt5_bridge_url),
        "mt5_native_configured": settings.has_mt5,
    }


# ──────────────────────────────────────────────────────────────
# Scheduler
# ──────────────────────────────────────────────────────────────

class SchedulerRequest(BaseModel):
    interval_minutes: int = 90


async def _scheduler_loop(interval_minutes: int):
    global _scheduler_running, _scheduler_cycles_run, _scheduler_last_run
    logger.info(f"Scheduler started — interval: {interval_minutes} min")

    # Import here to avoid circular imports
    from routes.cycle import _execute_cycle
    import uuid

    while _scheduler_running:
        from config import get_settings as _gs
        from tools.cycle_planner import get_scheduler_interval_minutes as _watcher_interval
        _s = _gs()
        if getattr(_s, "smart_watcher_enabled", True):
            interval = _watcher_interval(_s)
            interval_source = "cycle_planner"
        elif getattr(_s, "phase5_scheduler_adaptive", True):
            from tools.session_engine import get_scheduler_interval_minutes
            interval = get_scheduler_interval_minutes(_s)
            interval_source = "session_engine"
        else:
            interval = interval_minutes
            interval_source = "fixed"
        sleep_s = max(60, interval * 60)
        logger.info(
            "Scheduler sleeping %ss (~%.1f min, source=%s, smart_watcher=%s)",
            sleep_s, sleep_s / 60, interval_source,
            getattr(_s, "smart_watcher_enabled", True),
        )
        await asyncio.sleep(sleep_s)
        if not _scheduler_running:
            break

        cycle_id = str(uuid.uuid4())[:8]
        mode = get_effective_mode()
        logger.info(f"Scheduler trigger — cycle {cycle_id} in {mode} mode")

        try:
            await _execute_cycle(cycle_id, dry_run=(mode == "PAPER_MODE"))
            _scheduler_cycles_run += 1
            _scheduler_last_run = datetime.now(timezone.utc).isoformat()
            logger.info(f"Scheduler cycle {cycle_id} complete ({_scheduler_cycles_run} total)")
        except Exception as e:
            logger.error(f"Scheduler cycle failed: {e}")


@router.post("/scheduler/start")
async def start_scheduler(req: SchedulerRequest):
    global _scheduler_task, _scheduler_interval_minutes, _scheduler_running

    if _scheduler_running:
        return {
            "running": True,
            "interval_minutes": _scheduler_interval_minutes,
            "message": "Scheduler already running",
        }

    if req.interval_minutes < 1:
        raise HTTPException(400, "interval_minutes must be >= 1")

    _scheduler_interval_minutes = req.interval_minutes
    _scheduler_running = True
    _scheduler_task = asyncio.create_task(_scheduler_loop(req.interval_minutes))

    # Persist across restarts
    runtime_state.set_scheduler(True, req.interval_minutes)

    logger.info(f"Auto-cycle scheduler started: every {req.interval_minutes} min")
    return {
        "running": True,
        "interval_minutes": req.interval_minutes,
        "message": f"Scheduler started — will trigger cycle every {req.interval_minutes} minutes",
        "started_at": datetime.now(timezone.utc).isoformat(),
    }


@router.post("/scheduler/stop")
async def stop_scheduler():
    global _scheduler_task, _scheduler_running

    if not _scheduler_running:
        return {"running": False, "message": "Scheduler was not running"}

    _scheduler_running = False
    if _scheduler_task and not _scheduler_task.done():
        _scheduler_task.cancel()
        try:
            await _scheduler_task
        except asyncio.CancelledError:
            pass
    _scheduler_task = None

    # Persist across restarts
    runtime_state.set_scheduler(False, _scheduler_interval_minutes)

    logger.info("Auto-cycle scheduler stopped")
    return {
        "running": False,
        "cycles_completed": _scheduler_cycles_run,
        "last_run": _scheduler_last_run,
        "message": "Scheduler stopped",
    }


@router.get("/scheduler/status")
async def scheduler_status():
    return {
        "running": _scheduler_running,
        "interval_minutes": _scheduler_interval_minutes if _scheduler_running else None,
        "cycles_completed": _scheduler_cycles_run,
        "last_run": _scheduler_last_run,
    }


# ──────────────────────────────────────────────────────────────
# Live positions (from MT5 bridge if ACTIVE, from memory otherwise)
# ──────────────────────────────────────────────────────────────

@router.get("/positions/live")
async def get_live_positions():
    mode = get_effective_mode()
    if mode == "ACTIVE":
        try:
            positions = await mt5_bridge.get_live_positions()
            account = await mt5_bridge.get_live_account()
            return {
                "source": "mt5_live",
                "mode": mode,
                "positions": positions,
                "count": len(positions),
                "account": account,
            }
        except Exception as e:
            logger.warning(f"Could not fetch live MT5 positions: {e}")

    positions = memory.retrieve("open_positions") or []
    return {
        "source": "memory",
        "mode": mode,
        "positions": positions,
        "count": len(positions),
        "account": None,
    }


@router.post("/positions/{trade_id}/close")
async def close_position(trade_id: str):
    from config import get_settings
    from tools import account_state
    settings = get_settings()
    mode = get_effective_mode()

    positions = memory.retrieve("open_positions") or []

    # FAIL-CLOSED min-hold guard (FN anti-scalping). Returns blocking dict on
    # any uncertainty: not-in-memory, missing/malformed opened_at, age < 60s.
    blocked = account_state.check_min_hold(
        trade_id, positions, settings.min_position_hold_seconds
    )
    if blocked is not None:
        return {**blocked, "trade_id": trade_id, "mode": mode}

    result = await mt5_bridge.close_trade(trade_id, mode)

    closed = next((p for p in positions if str(p.get("trade_id")) == trade_id), None)
    updated = [p for p in positions if str(p.get("trade_id")) != trade_id]
    if result.get("success"):
        memory.store("open_positions", updated)

    if closed is not None and result.get("success"):
        try:
            from tools import close_logger
            bridge = (settings.mt5_bridge_url or "").rstrip("/") or None
            await close_logger.log_position_closed(
                closed,
                account_id="primary",
                bridge_url=bridge,
                source="manual_api",
            )
        except Exception:
            logger.exception("Failed to log trade outcome")

    return {
        **result,
        "trade_id": trade_id,
        "mode": mode,
        "remaining_in_memory": len(updated),
    }


@router.get("/debug/mt5")
async def debug_mt5():
    """Diagnostic endpoint — tests MT5 native connectivity and returns detailed info."""
    return await mt5_bridge.diagnose_mt5()
