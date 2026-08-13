"""V11 Trading Council status endpoint."""
from __future__ import annotations

from fastapi import APIRouter

from config import get_settings
from tools import memory
from tools.strategy_router import route_market_mode
from tools.session_engine import get_profile
from tools.universe_manager import universe_status
from tools.session_24h import is_24h_all_systems

router = APIRouter()


@router.get("/council/status")
async def council_status():
    settings = get_settings()
    profile = get_profile(settings)
    route = route_market_mode(settings, profile)
    report = memory.retrieve("council_last_report") or {}
    uni = universe_status(settings)
    rejected = report.get("rejected") or []
    veto_reasons = [r.get("vetoes") for r in rejected if r.get("vetoes")]
    return {
        "council_enabled": settings.council_enabled,
        "council_mode": getattr(settings, "council_mode", "shadow"),
        "full_power_24h": is_24h_all_systems(settings),
        "configured_symbols_count": uni.get("configured_symbols_count"),
        "active_symbols_count": uni.get("active_symbols_count"),
        "symbols_analyzed": report.get("scanned_symbols_count", 0),
        "council_approved": report.get("approved", []),
        "council_approved_count": report.get("approved_count", len(report.get("approved") or [])),
        "risk_vetoes": veto_reasons,
        "rejected_reasons": [
            {"symbol": r.get("symbol"), "vetoes": r.get("vetoes"), "meta_score": r.get("meta_score")}
            for r in rejected
        ],
        "strategy_router": route,
        "session_profile": profile,
        "universe": {
            "configured_symbols_count": uni.get("configured_symbols_count"),
            "active_symbols_count": uni.get("active_symbols_count"),
            "asset_class_counts": uni.get("asset_class_counts"),
        },
        "funnel": {
            "deep_analysis_top_n": getattr(settings, "deep_analysis_top_n", 15),
            "council_top_n": getattr(settings, "council_top_n", 8),
            "council_full_universe_debug": getattr(settings, "council_full_universe_debug", False),
        },
        "last_run": report,
        "scanned_symbols_count": report.get("scanned_symbols_count", 0),
        "council_evaluated_count": report.get("council_evaluated_count", 0),
        "top_candidates": report.get("top_candidates", [])[:10],
        "approved": report.get("approved", []),
        "rejected": report.get("rejected", []),
        "veto_reasons": veto_reasons,
    }
