"""V11 universe status endpoint."""
from __future__ import annotations

from fastapi import APIRouter

from config import get_settings
from tools.universe_manager import universe_status
from tools.currency_exposure import build_exposure_report
from tools.session_24h import is_24h_all_systems
from tools import memory

router = APIRouter()


@router.get("/universe/status")
async def universe_status_endpoint():
    settings = get_settings()
    status = universe_status(settings)
    exposure = build_exposure_report()
    scalp = memory.retrieve("scalp_last_report") or {}
    council = memory.retrieve("council_last_report") or {}
    return {
        **status,
        "full_power_24h": is_24h_all_systems(settings),
        "scalping_mode": settings.scalping_mode,
        "council_mode": getattr(settings, "council_mode", "shadow"),
        "symbols_analyzed": scalp.get("scanned_symbols_count") or council.get("scanned_symbols_count", 0),
        "exposure": exposure,
        "exposure_by_currency": exposure.get("exposure_by_currency", {}),
    }
