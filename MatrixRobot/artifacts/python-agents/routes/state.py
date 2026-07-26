import hmac
from fastapi import APIRouter, HTTPException, Request
from config import get_settings
from models.schemas import AgentState
from tools import memory, correlation, economic_calendar, prop_rules, account_state
from tools import adaptive_policy as _ape

router = APIRouter()


@router.get("/session/status")
async def get_session_status():
    """Phase 5 + Smart Watcher — session profile and cycle planning."""
    from tools.session_engine import get_profile
    from tools.cycle_planner import plan_cycle
    from routes.trading import get_effective_mode

    settings = get_settings()
    mode = get_effective_mode()
    profile = get_profile(settings)
    plan = plan_cycle(mode, settings)
    return {
        "phase5_intraday_enabled": settings.phase5_intraday_enabled,
        "session_filter_mode": settings.session_filter_mode,
        "smart_watcher_enabled": settings.smart_watcher_enabled,
        "smart_watcher_execute_off_session_small": settings.smart_watcher_execute_off_session_small,
        "trading_profile": getattr(settings, "trading_profile", "conservative"),
        "primary_timeframe": getattr(settings, "primary_timeframe", "H1"),
        "symbol_count": len(settings.symbol_list),
        "active_disabled_symbols": sorted(settings.active_disabled_symbol_set),
        "position_manager_enabled": settings.phase5_position_manager_enabled,
        "scheduler_adaptive": settings.phase5_scheduler_adaptive,
        "brain_active": plan.get("brain_active"),
        "cycle_type": plan.get("cycle_type"),
        "next_full_cycle_at": plan.get("next_full_cycle_at"),
        "next_killzone": plan.get("next_killzone"),
        "scheduler_interval_minutes": plan.get("scheduler_interval_minutes"),
        "estimated_cost_saved_today": (plan.get("watcher_stats") or {}).get(
            "estimated_cost_saved_usd", 0.0,
        ),
        "watcher_stats": plan.get("watcher_stats"),
        "profile": profile,
    }


@router.get("/adaptive-policy")
async def get_adaptive_policy():
    """Adaptive Policy Envelope (APE) snapshot.

    Shows what the brain has autonomously changed:
      - risk_multiplier: current position-size multiplier (1.0 = baseline)
      - paused_symbols: symbols the brain temporarily blocked
      - conviction_override: tightened entry threshold if set
      - adaptation_log: last 20 autonomous brain decisions with full reasoning
      - allowed / forbidden: what the brain can/cannot change on its own
    """
    return _ape.get_snapshot()


@router.get("/analytics")
async def get_analytics():
    """Snapshot of the advanced analytics layer for dashboard/debug use.

    Returns the latest indicators, multi-timeframe consensus, volatility
    regimes, correlation report, and economic calendar from the last cycle.
    Falls back to a live calendar+correlation snapshot if no cycle has run.
    """
    settings = get_settings()
    last = memory.get_last_cycle() or {}
    cal = last.get("economic_calendar") or economic_calendar.get_calendar().model_dump()
    corr = last.get("correlation_report") or correlation.build_report().model_dump()
    return {
        "cycle_id": last.get("cycle_id"),
        "finished_at": last.get("finished_at"),
        "config": {
            "multi_timeframe_enabled": settings.multi_timeframe_enabled,
            "mtf_required_alignment": settings.mtf_required_alignment,
            "correlation_guard_enabled": settings.correlation_guard_enabled,
            "volatility_regime_enabled": settings.volatility_regime_enabled,
            "economic_calendar_enabled": settings.economic_calendar_enabled,
            "economic_calendar_pre_event_minutes": settings.economic_calendar_pre_event_minutes,
            "ict_smc_enabled": settings.ict_smc_enabled,
            "ict_min_confluence": settings.ict_min_confluence,
            "ict_ensemble_weight": settings.ict_ensemble_weight,
        },
        "indicators": last.get("indicators", {}),
        "mtf": last.get("mtf", {}),
        "ict": last.get("ict", {}),
        "ict_summaries": last.get("ict_summaries", {}),
        "volatility_regimes": last.get("volatility_regimes", {}),
        "correlation_report": corr,
        "economic_calendar": cal,
    }


@router.get("/prop-status")
async def get_prop_status():
    """Full FundedNext (or configured prop firm) compliance snapshot.

    Combines the live MT5 account, internal stricter risk targets, prop-firm
    hard caps, trading-day tracker, and consistency-rule status into one
    dashboard-ready payload.
    """
    status = await prop_rules.evaluate()
    acct = await account_state.refresh_account()
    return {
        "firm": status.firm,
        "plan": status.plan,
        "phase": status.phase,
        "compliant": status.compliant,
        "can_trade": status.can_trade,
        "block_reason": status.block_reason,
        "account": acct,
        "drawdown": {
            "daily_pct": status.daily_loss_pct,
            "daily_internal_target_pct": status.daily_loss_internal_target_pct,
            "daily_hard_cap_pct": status.daily_loss_hard_cap_pct,
            "daily_buffer_pct": status.daily_buffer_pct,
            "total_pct": status.total_loss_pct,
            "total_internal_target_pct": status.total_loss_internal_target_pct,
            "total_hard_cap_pct": status.total_loss_hard_cap_pct,
            "total_buffer_pct": status.total_buffer_pct,
        },
        "profit": {
            "current_pct": status.profit_pct,
            "target_pct": status.profit_target_pct,
        },
        "trading_days": {
            "completed": status.trading_days_completed,
            "required": status.trading_days_required,
            "dates": account_state.trading_days_list(),
        },
        "consistency": {
            "ratio": status.consistency_ratio,
            "max_pct": status.consistency_max_pct,
            "ok": status.consistency_ok,
        },
        "trades_today": status.trades_today,
        "trades_today_max": status.trades_today_max,
        "min_position_hold_seconds": status.min_position_hold_seconds,
        "daily_profit_pct": status.daily_profit_pct,
        "daily_profit_cap_pct": status.daily_profit_cap_pct,
        "warnings": status.warnings,
        "violations": status.violations,
    }


@router.get("/state", response_model=AgentState)
async def get_agent_state():
    settings = get_settings()
    cached = memory.get_state()

    if cached:
        return AgentState(
            mode=cached.get("mode", settings.trading_state),
            last_cycle_id=cached.get("last_cycle_id"),
            last_cycle_at=cached.get("last_cycle_at"),
            last_decision=cached.get("last_decision"),
            daily_drawdown_pct=cached.get("daily_drawdown_pct", 0.0),
            total_drawdown_pct=cached.get("total_drawdown_pct", 0.0),
            open_positions=len(memory.retrieve("open_positions") or []),
            cycles_today=cached.get("cycles_today", 0),
            is_ready=cached.get("is_ready", True),
        )

    return AgentState(
        mode=settings.trading_state,
        is_ready=True,
        open_positions=len(memory.retrieve("open_positions") or []),
    )


@router.get("/signals")
async def get_signals():
    last = memory.get_last_cycle()
    if not last:
        raise HTTPException(status_code=404, detail="No cycles completed yet")

    return {
        "cycle_id": last.get("cycle_id"),
        "timestamp": last.get("finished_at"),
        "mode": last.get("mode"),
        "decision": last.get("decision"),
        "execution": last.get("execution"),
        "symbols_analyzed": last.get("symbols_analyzed", []),
        "duration_ms": last.get("duration_ms"),
    }


@router.get("/positions")
async def get_positions():
    positions = memory.retrieve("open_positions") or []
    return {"positions": positions, "count": len(positions)}


@router.delete("/positions/{trade_id}")
async def close_position(trade_id: str, request: Request):
    """Close (remove from memory) a position by trade_id.

    AUTH: Primary guard = api_secret_guard middleware in main.py (covers all
    DELETE/POST/PUT/PATCH). This route also enforces a secondary check for
    defence-in-depth so auth holds even if middleware is ever bypassed.
    """
    settings = get_settings()
    secret = settings.mt5_bridge_secret
    # Secondary (belt-and-suspenders) auth check at route level.
    if secret:
        provided = request.headers.get("X-Brain-Secret", "")
        try:
            match = hmac.compare_digest(provided.encode(), secret.encode())
        except Exception:
            match = False
        if not match:
            raise HTTPException(status_code=401, detail="Unauthorized — invalid X-Brain-Secret")
    positions = memory.retrieve("open_positions") or []

    # FAIL-CLOSED min-hold guard (shared helper — identical to /agents/positions/{id}/close)
    blocked = account_state.check_min_hold(
        trade_id, positions, settings.min_position_hold_seconds
    )
    if blocked is not None:
        return blocked

    closed = next((p for p in positions if p.get("trade_id") == trade_id), None)
    updated = [p for p in positions if p.get("trade_id") != trade_id]
    memory.store("open_positions", updated)

    if closed is not None:
        try:
            memory.log_trade_outcome({
                "trade_id": trade_id,
                "symbol": closed.get("symbol"),
                "side": closed.get("side") or closed.get("type"),
                "entry": closed.get("entry") or closed.get("price"),
                "exit": None,
                "pnl": None,
                "reason": "manual_close_memory_only",
            })
        except Exception:
            pass

    return {"success": True, "message": f"Position {trade_id} closed", "remaining": len(updated)}
