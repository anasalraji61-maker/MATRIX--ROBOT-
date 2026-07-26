"""Off-session SMALL trade caps (extended demo mode)."""
from __future__ import annotations

from tools import memory
from tools.prop_time import prop_server_today
from tools.symbol_registry import FOREX_SET, INDICES, METALS, OIL


def is_off_session(profile: dict, settings=None) -> bool:
    from config import get_settings

    s = settings or get_settings()
    return (
        str(getattr(s, "session_filter_mode", "")).lower() == "extended"
        and profile.get("active_killzone") == "none"
        and getattr(s, "allow_off_session_small_trades", True)
    )


def asset_allowed_off_session(symbol: str, settings=None) -> bool:
    from config import get_settings
    from tools.session_24h import is_24h_all_systems

    s = settings or get_settings()
    sym = symbol.upper()
    mode = str(getattr(s, "off_session_allowed_assets", "FX_ONLY")).upper()
    if is_24h_all_systems(s) and mode == "ALL":
        if sym in INDICES and getattr(s, "tiered_block_indices_outside_kz", True):
            return False
        return sym in FOREX_SET or sym in METALS or sym in OIL
    if mode == "FX_ONLY":
        return sym in FOREX_SET
    return sym in FOREX_SET or sym in METALS or sym in OIL or sym in INDICES


def trades_today_count() -> int:
    data = memory.retrieve("off_session_trades_today") or {}
    if data.get("date") != prop_server_today():
        return 0
    return int(data.get("count", 0))


def record_trade_opened() -> int:
    today = prop_server_today()
    data = memory.retrieve("off_session_trades_today") or {}
    if data.get("date") != today:
        data = {"date": today, "count": 0}
    data["count"] = int(data.get("count", 0)) + 1
    memory.store("off_session_trades_today", data, ttl_seconds=86400 * 2)
    return data["count"]


def scanner_may_execute_off_session_small(
    mode: str,
    cycle_plan: dict,
    settings=None,
) -> bool:
    """True when scanner cycle is allowed to place SMALL trades outside killzone."""
    from config import get_settings

    s = settings or get_settings()
    if not getattr(s, "smart_watcher_execute_off_session_small", False):
        return False
    if not getattr(s, "allow_off_session_small_trades", True):
        return False
    if mode != "ACTIVE":
        return False
    if str(getattr(s, "session_filter_mode", "")).lower() != "extended":
        return False
    if cycle_plan.get("cycle_type") != "scanner":
        return False
    if cycle_plan.get("active_killzone") != "none":
        return False
    return True
