"""V11 Council Agent — runs Matrix Trading Council after analysis."""
from __future__ import annotations

import logging

from config import get_settings
from tools.trading_council import run_full_council

logger = logging.getLogger("matrix.council_agent")


async def run(state: dict) -> dict:
    settings = get_settings()
    if not getattr(settings, "council_enabled", True):
        return {**state, "council_report": {"council_enabled": False}}

    report = run_full_council(state, settings)
    mode = str(getattr(settings, "council_mode", "shadow") or "shadow").lower()

    council_approved = report.get("approved") or []
    if mode == "enforce" and council_approved:
        approved_symbols = {a["symbol"] for a in council_approved}
        filtered_analyses = [
            a for a in (state.get("analyses") or [])
            if a.get("symbol") in approved_symbols
        ]
        if filtered_analyses:
            state = {**state, "analyses": filtered_analyses}
            best = max(filtered_analyses, key=lambda x: float(x.get("strength") or 0))
            state["best_analysis"] = best

    if mode == "advisory" and council_approved:
        try:
            from tools import telegram_alerts
            if settings.has_telegram:
                lines = ["V11 Council Advisory"]
                for a in council_approved[:3]:
                    meta = (a.get("council") or {}).get("meta") or {}
                    lines.append(
                        f"{a['symbol']} {meta.get('final_action', a.get('signal'))} "
                        f"style={meta.get('trade_style')} conf={meta.get('confidence', 0):.2f}"
                    )
                await telegram_alerts.send("\n".join(lines), level="info")
        except Exception as e:
            logger.debug("council advisory telegram: %s", e)

    return {**state, "council_report": report}
