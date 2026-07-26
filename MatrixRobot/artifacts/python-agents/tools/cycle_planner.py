"""Smart Watcher — cycle type planning (full / scanner / maintenance)."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from tools.ict_smc import KILLZONES_UTC
from tools.session_engine import get_profile, _active_killzone


# UTC hour when each killzone starts (for next_full_cycle_at)
_KILLZONE_START_UTC = {
    "asian": 23,
    "london": 7,
    "newyork": 12,
}


def next_killzone_start(now: datetime | None = None) -> tuple[datetime, str]:
    """Return (utc_datetime, killzone_name) of the next session window."""
    now = now or datetime.now(timezone.utc)
    hour = now.hour

    # Next window in chronological order from current hour
    schedule = [(7, "london"), (12, "newyork"), (23, "asian")]
    for start_h, name in schedule:
        if hour < start_h:
            return now.replace(hour=start_h, minute=0, second=0, microsecond=0), name

    # After 23:00 or before 07:00 next day → asian tonight or london tomorrow
    if hour >= 23:
        return now.replace(hour=7, minute=0, second=0, microsecond=0) + timedelta(days=1), "london"
    if hour < 4:
        return now.replace(hour=7, minute=0, second=0, microsecond=0), "london"
    if hour < 7:
        return now.replace(hour=7, minute=0, second=0, microsecond=0), "london"
    if hour < 12:
        return now.replace(hour=12, minute=0, second=0, microsecond=0), "newyork"
    if hour < 15:
        return now.replace(hour=23, minute=0, second=0, microsecond=0), "asian"
    return now.replace(hour=23, minute=0, second=0, microsecond=0), "asian"


def _open_position_count() -> int:
    try:
        from tools import memory
        return len(memory.retrieve("open_positions") or [])
    except Exception:
        return 0


def _watcher_stats() -> dict:
    try:
        from tools import memory
        from tools.prop_time import prop_server_today
        today = prop_server_today()
        stats = memory.retrieve("watcher_stats") or {}
        if stats.get("date") != today:
            return {
                "date": today,
                "full_cycles": 0,
                "scanner_cycles": 0,
                "maintenance_cycles": 0,
                "brain_escalations": 0,
                "estimated_cost_saved_usd": 0.0,
            }
        return stats
    except Exception:
        return {
            "date": "",
            "full_cycles": 0,
            "scanner_cycles": 0,
            "maintenance_cycles": 0,
            "brain_escalations": 0,
            "estimated_cost_saved_usd": 0.0,
        }


def record_cycle_type(cycle_type: str, *, escalated: int = 0) -> dict:
    """Increment daily counters and return updated stats."""
    from tools import memory
    from tools.prop_time import prop_server_today
    from config import get_settings

    s = get_settings()
    stats = _watcher_stats()
    stats["date"] = prop_server_today()
    full_cost = float(getattr(s, "estimated_full_cycle_cost_usd", 0.18))
    scanner_cost = float(getattr(s, "estimated_scanner_cycle_cost_usd", 0.02))
    maint_cost = float(getattr(s, "estimated_maintenance_cycle_cost_usd", 0.005))
    escalation_cost = float(getattr(s, "estimated_brain_escalation_cost_usd", 0.06))

    if cycle_type == "full":
        stats["full_cycles"] = stats.get("full_cycles", 0) + 1
    elif cycle_type == "scanner":
        stats["scanner_cycles"] = stats.get("scanner_cycles", 0) + 1
        stats["estimated_cost_saved_usd"] = round(
            stats.get("estimated_cost_saved_usd", 0.0) + max(0, full_cost - scanner_cost),
            4,
        )
        if escalated:
            stats["brain_escalations"] = stats.get("brain_escalations", 0) + escalated
            stats["estimated_cost_saved_usd"] = round(
                stats["estimated_cost_saved_usd"]
                - escalated * escalation_cost
                + escalated * (full_cost - escalation_cost),
                4,
            )
    elif cycle_type == "maintenance":
        stats["maintenance_cycles"] = stats.get("maintenance_cycles", 0) + 1
        stats["estimated_cost_saved_usd"] = round(
            stats.get("estimated_cost_saved_usd", 0.0) + max(0, full_cost - maint_cost),
            4,
        )

    memory.store("watcher_stats", stats, ttl_seconds=86400 * 2)
    return stats


def plan_cycle(mode: str = "", settings=None) -> dict[str, Any]:
    """Decide cycle_type and scheduling metadata for the next run."""
    from config import get_settings
    from tools.universe_manager import is_full_power
    from tools.session_24h import is_24h_all_systems

    s = settings or get_settings()
    profile = get_profile(s)
    kz = profile.get("active_killzone", "none")
    shadow = bool(profile.get("shadow_mode", False))
    open_count = _open_position_count()
    next_at, next_kz = next_killzone_start()
    stats = _watcher_stats()

    # V11 Full Power / 24h — always full brain cycle, 24/5
    if is_full_power(s) or is_24h_all_systems(s) or getattr(s, "run_24h_full_analysis", False):
        if kz in ("london", "newyork"):
            interval = int(s.phase5_scheduler_high_liq_minutes)
        elif kz == "asian":
            interval = int(s.phase5_scheduler_medium_liq_minutes)
        else:
            interval = int(s.phase5_scheduler_low_liq_minutes)
        return {
            "cycle_type": "full",
            "brain_active": True,
            "scheduler_interval_minutes": interval,
            "active_killzone": kz,
            "shadow_mode": shadow,
            "open_positions": open_count,
            "next_full_cycle_at": next_at.isoformat(),
            "next_killzone": next_kz,
            "watcher_stats": stats,
            "full_power_24h": True,
            "run_24h_all_systems": is_24h_all_systems(s),
            "killzones_utc": KILLZONES_UTC,
        }

    if not getattr(s, "smart_watcher_enabled", True):
        return {
            "cycle_type": "full",
            "brain_active": True,
            "scheduler_interval_minutes": int(profile.get("scheduler_interval_minutes", 90)),
            "active_killzone": kz,
            "shadow_mode": shadow,
            "open_positions": open_count,
            "next_full_cycle_at": next_at.isoformat(),
            "next_killzone": next_kz,
            "watcher_stats": stats,
        }

    # Inside London or NY → full brain
    if kz in ("london", "newyork"):
        cycle_type = "full"
        brain_active = True
        interval = int(s.phase5_scheduler_high_liq_minutes)
    # Asian → full brain (SMALL trades via tiered session)
    elif kz == "asian":
        cycle_type = "full"
        brain_active = True
        interval = int(s.phase5_scheduler_medium_liq_minutes)
    # Outside killzone
    elif open_count > 0:
        cycle_type = "maintenance"
        brain_active = False
        interval = int(getattr(s, "off_session_maintenance_minutes", 12))
    else:
        cycle_type = "scanner"
        brain_active = False
        interval = int(getattr(s, "off_session_scanner_minutes", 25))

    return {
        "cycle_type": cycle_type,
        "brain_active": brain_active,
        "scheduler_interval_minutes": interval,
        "active_killzone": kz,
        "shadow_mode": shadow,
        "open_positions": open_count,
        "next_full_cycle_at": next_at.isoformat(),
        "next_killzone": next_kz,
        "watcher_stats": stats,
        "killzones_utc": KILLZONES_UTC,
    }


def get_scheduler_interval_minutes(settings=None) -> int:
    """Adaptive scheduler interval including Smart Watcher logic."""
    from config import get_settings
    import runtime_state

    s = settings or get_settings()
    mode = runtime_state.get_mode() or s.trading_state
    return int(plan_cycle(mode, s)["scheduler_interval_minutes"])
