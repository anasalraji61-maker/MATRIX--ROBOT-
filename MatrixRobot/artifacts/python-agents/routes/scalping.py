"""V11 scalping status endpoint."""
from __future__ import annotations

from fastapi import APIRouter

from config import get_settings
from tools import memory
from tools.scalp_engine import get_last_scalp_report
from tools.scalp_risk import count_scalp_open, scalp_trades_today
from tools.scalping_guard import scalping_effective_enabled
from tools.universe_manager import universe_status
from tools.session_24h import is_24h_all_systems

router = APIRouter()


@router.get("/scalping/status")
async def scalping_status():
    settings = get_settings()
    enabled, reason = scalping_effective_enabled(settings.trading_state, settings)
    report = get_last_scalp_report()
    uni = universe_status(settings)
    return {
        "scalping_enabled": enabled,
        "scalping_effective": enabled,
        "scalping_demo_only": settings.scalping_demo_only,
        "scalping_mode": settings.scalping_mode,
        "full_power_24h": is_24h_all_systems(settings),
        "disabled_reason": reason if not enabled else None,
        "configured_symbols_count": uni.get("configured_symbols_count"),
        "active_symbols_count": uni.get("active_symbols_count"),
        "scanned_symbols_count": report.get("scanned_symbols_count", 0),
        "scalping_candidates_count": report.get("scalping_candidates_count", 0),
        "top_scalping_candidates": report.get("top_scalping_candidates", [])[:10],
        "scalping_approved": report.get("scalping_approved", []),
        "scalping_rejected_reasons": report.get("scalping_rejected_reasons", {}),
        "exposure_by_currency": report.get("exposure_by_currency", {}),
        "blocked_by_correlation": report.get("blocked_by_correlation", []),
        "scalp_trades_opened": report.get("scalp_trades_opened", 0),
        "execution_rejections": memory.retrieve("scalp_execution_rejections") or {},
        "config": {
            "max_trades_per_day": settings.scalping_max_trades_per_day,
            "max_open_trades": settings.scalping_max_open_trades,
            "risk_multiplier": settings.scalping_risk_multiplier,
            "min_strength": settings.scalping_min_strength,
            "min_rr": settings.scalping_min_rr,
            "timeframes": settings.scalping_timeframes,
            "allowed_assets": settings.scalping_allowed_assets,
            "max_hold_minutes": settings.scalping_max_hold_minutes,
        },
        "daily": {
            "trades_opened_today": scalp_trades_today(),
            "open_scalp_positions": count_scalp_open(),
        },
        "last_run": report,
    }