"""Phase 5 — position manager agent (runs early each cycle)."""
from __future__ import annotations

import logging

from config import get_settings
from tools.position_manager import manage_open_positions
from tools.session_engine import get_profile

logger = logging.getLogger("matrix.position_manager_agent")


async def run(state: dict) -> dict:
    settings = get_settings()
    mode = state.get("mode", settings.trading_state)
    session = get_profile(settings)

    pm_result = {"actions": [], "session": session}
    if settings.phase5_position_manager_enabled and mode != "FROZEN":
        try:
            pm_result = await manage_open_positions(mode, settings=settings)
            from tools.scalp_position_manager import manage_scalp_positions
            scalp_pm = await manage_scalp_positions(state)
            if scalp_pm.get("actions"):
                pm_result["scalp_actions"] = scalp_pm["actions"]
                pm_result["scalp_closed"] = scalp_pm.get("closed", 0)
        except Exception as e:
            logger.exception("Position manager failed")
            pm_result = {"actions": [], "session": session, "error": str(e)}

    return {
        **state,
        "session_profile": session,
        "position_management": pm_result,
    }
