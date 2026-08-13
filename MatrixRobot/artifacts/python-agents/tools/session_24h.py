"""24/5 all-systems mode — scalping, intraday, swing, all tiers, full analysis."""
from __future__ import annotations

from config import get_settings


def is_24h_all_systems(settings=None) -> bool:
    """True when every trading system may run outside killzones (demo full-power)."""
    s = settings or get_settings()
    if getattr(s, "run_24h_all_systems", False):
        return True
    if str(getattr(s, "session_filter_mode", "") or "").lower() == "24h":
        return True
    from tools.universe_manager import is_full_power
    if is_full_power(s) and (
        getattr(s, "run_24h_full_analysis", False)
        or getattr(s, "run_24h_all_systems", False)
    ):
        return True
    return False
