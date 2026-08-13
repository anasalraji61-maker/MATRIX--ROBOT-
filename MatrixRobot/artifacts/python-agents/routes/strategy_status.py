"""V11 strategy router + performance status."""
from __future__ import annotations

from fastapi import APIRouter

from config import get_settings
from tools import memory
from tools.scalp_engine import get_last_scalp_report
from tools.strategy_router import route_market_mode
from tools.session_engine import get_profile
from tools.strategy_scoring import get_scores
from tools.universe_manager import universe_status
from tools.session_24h import is_24h_all_systems

router = APIRouter()


@router.get("/strategy/status")
async def strategy_status():
    settings = get_settings()
    profile = get_profile(settings)
    route = route_market_mode(settings, profile)
    scalp = get_last_scalp_report()
    council = memory.retrieve("council_last_report") or {}
    scores = get_scores(window=50)
    uni = universe_status(settings)
    exec_rej = memory.retrieve("scalp_execution_rejections") or {}
    return {
        "trading_mode_profile": getattr(settings, "trading_mode_profile", ""),
        "full_power_24h": is_24h_all_systems(settings),
        "configured_symbols_count": uni.get("configured_symbols_count"),
        "active_symbols_count": uni.get("active_symbols_count"),
        "scalping_mode": settings.scalping_mode,
        "council_mode": getattr(settings, "council_mode", "shadow"),
        "symbols_analyzed": scalp.get("scanned_symbols_count") or council.get("scanned_symbols_count", 0),
        "scalp_candidates": scalp.get("scalping_candidates_count", 0),
        "council_approved": council.get("approved_count", len(council.get("approved") or [])),
        "risk_vetoes": [
            r.get("vetoes") for r in (council.get("rejected") or []) if r.get("vetoes")
        ],
        "trades_opened_by_strategy": _trades_opened_by_strategy(scalp),
        "rejected_reasons": {
            **(scalp.get("scalping_rejected_reasons") or {}),
            **exec_rej,
        },
        "strategy_router": route,
        "last_scalp_by_strategy": _group_by_strategy(scalp),
        "council_approved_count": council.get("approved_count", 0),
        "strategy_scores": scores,
        "scalp_trades_opened": scalp.get("scalp_trades_opened", 0),
    }


def _group_by_strategy(scalp_report: dict) -> dict:
    out: dict[str, int] = {}
    for c in scalp_report.get("top_scalping_candidates") or []:
        name = c.get("strategy") or c.get("strategy_name") or "unknown"
        out[name] = out.get(name, 0) + 1
    return out


def _trades_opened_by_strategy(scalp_report: dict) -> dict:
    out: dict[str, int] = {}
    for c in scalp_report.get("scalping_approved") or []:
        name = c.get("strategy") or c.get("strategy_name") or "scalp"
        out[name] = out.get(name, 0) + 1
    opened = int(scalp_report.get("scalp_trades_opened") or 0)
    if opened and not out:
        out["scalp"] = opened
    return out
