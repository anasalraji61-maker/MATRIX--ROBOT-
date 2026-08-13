"""Phase 5A — session / liquidity profile for intraday adaptive trading."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from tools.ict_smc import KILLZONES_UTC, _active_killzone
from tools.symbol_registry import INDICES, METALS, OIL


def _is_24h(s) -> bool:
    from tools.session_24h import is_24h_all_systems
    return is_24h_all_systems(s)


def _liquidity_tier(killzone: str) -> str:
    if killzone in ("london", "newyork"):
        return "high"
    if killzone == "asian":
        return "medium"
    hour = datetime.now(timezone.utc).hour
    if hour in (10, 11, 15, 16, 17):
        return "medium"
    return "low"


def _asset_class(symbol: str) -> str:
    sym = symbol.upper()
    if sym in INDICES:
        return "indices"
    if sym in METALS:
        return "metals"
    if sym in OIL:
        return "oil"
    return "fx"


def check_symbol_session_allowed(
    symbol: str,
    trade_tier: str,
    profile: dict,
    settings=None,
) -> tuple[bool, str, bool]:
    """Return (allowed, reason, off_session_shadow).

    off_session_shadow=True when the candidate would be logged but not executed
    (outside killzone / shadow mode).
    """
    from config import get_settings

    s = settings or get_settings()
    sym = symbol.upper()
    tier = trade_tier.upper()
    mode = str(getattr(s, "session_filter_mode", "tiered")).lower()

    if not profile.get("enabled", True):
        return True, "", False

    if mode == "off" or _is_24h(s):
        if _is_24h(s) and sym in INDICES and getattr(s, "tiered_block_indices_outside_kz", True):
            return False, "Indices disabled until MT5 verified", False
        if _is_24h(s) and tier == "NORMAL" and not getattr(s, "allow_24h_normal_trades", True):
            return False, "24h NORMAL trades disabled by config", False
        if _is_24h(s):
            return True, "", False

    if mode == "off":
        return True, "", False

    if mode == "strict":
        if not profile.get("allow_new_trades", True):
            return False, profile.get("reason", "Session gate paused"), True
        return True, "", False

    # tiered (default)
    kz = profile.get("active_killzone", "none")
    liquidity = profile.get("liquidity", "low")

    if kz in ("london", "newyork"):
        return True, "", False

    if kz == "asian":
        if tier == "NORMAL":
            return False, "Asian session — NORMAL paused (SMALL only)", False
        if tier == "SMALL":
            if sym in INDICES and getattr(s, "tiered_block_indices_outside_kz", True):
                return False, "Indices disabled until broker data verified", False
            if sym in OIL and getattr(s, "tiered_block_oil_outside_kz", True):
                return False, "Oil disabled outside London/NY", False
            return True, "", False
        return False, f"Asian session — {tier} tier not allowed", False

    # Outside killzone / low liquidity
    mode = str(getattr(s, "session_filter_mode", "tiered")).lower()
    if mode == "extended" and kz == "none":
        if tier != "SMALL":
            return False, "Off-session — NORMAL paused (SMALL only)", False
        if getattr(s, "tiered_block_metals_outside_kz", True) and sym in METALS:
            return False, "Off-session — metals paused", False
        if getattr(s, "tiered_block_oil_outside_kz", True) and sym in OIL:
            return False, "Off-session — oil paused", False
        if getattr(s, "tiered_block_indices_outside_kz", True) and sym in INDICES:
            return False, "Off-session — indices paused", False
        return True, "", False

    if getattr(s, "tiered_block_metals_outside_kz", True) and sym in METALS:
        return False, "Outside killzone — metals paused", True
    if getattr(s, "tiered_block_oil_outside_kz", True) and sym in OIL:
        return False, "Outside killzone — oil paused", True
    if getattr(s, "tiered_block_indices_outside_kz", True) and sym in INDICES:
        return False, "Outside killzone — indices paused", True

    if getattr(s, "phase5_block_low_liquidity", True) and liquidity == "low":
        return False, profile.get("reason", "Outside ICT killzone — shadow only"), True

    if getattr(s, "phase5_session_require_killzone", True) and kz == "none":
        return False, profile.get("reason", "Outside ICT killzone — shadow only"), True

    return False, profile.get("reason", "Session gate"), True


def get_profile(settings=None) -> dict[str, Any]:
    """Return current session profile used by scheduler, risk, and execution."""
    from config import get_settings

    s = settings or get_settings()
    now = datetime.now(timezone.utc)
    kz = _active_killzone(now)
    tier = _liquidity_tier(kz)
    session_mode = str(getattr(s, "session_filter_mode", "tiered")).lower()

    if getattr(s, "phase5_session_require_killzone", True) and kz == "none":
        tier = "low"

    if not getattr(s, "phase5_intraday_enabled", True):
        return {
            "enabled": False,
            "session_filter_mode": session_mode,
            "liquidity": "normal",
            "active_killzone": kz,
            "allow_new_trades": True,
            "allow_normal_trades": True,
            "allow_small_trades": True,
            "shadow_mode": False,
            "scheduler_interval_minutes": int(s.scheduler_interval_minutes),
            "sl_atr_mult": 1.5,
            "tp_rr_ratio": 2.0,
            "utc_hour": now.hour,
            "reason": "Phase 5 disabled — legacy sizing",
        }

    if tier == "high":
        sl_mult = float(s.phase5_sl_atr_mult_high)
        tp_rr = float(s.phase5_tp_rr_high)
        interval = int(s.phase5_scheduler_high_liq_minutes)
    elif tier == "medium":
        sl_mult = float(s.phase5_sl_atr_mult_medium)
        tp_rr = float(s.phase5_tp_rr_medium)
        interval = int(s.phase5_scheduler_medium_liq_minutes)
    else:
        sl_mult = float(s.phase5_sl_atr_mult_low)
        tp_rr = float(s.phase5_tp_rr_low)
        interval = int(s.phase5_scheduler_low_liq_minutes)

    allow = True
    allow_normal = True
    allow_small = True
    shadow_mode = False
    reasons: list[str] = []

    if session_mode == "strict":
        if getattr(s, "phase5_block_low_liquidity", True) and tier == "low":
            allow = False
            reasons.append("Low-liquidity window — new entries paused")
        if getattr(s, "phase5_session_require_killzone", True) and kz == "none":
            allow = False
            reasons.append("Outside ICT killzone — new entries paused")
    elif session_mode == "tiered":
        if kz in ("london", "newyork"):
            allow = True
            allow_normal = True
            allow_small = True
        elif kz == "asian":
            allow = True
            allow_normal = False
            allow_small = True
            reasons.append("Asian session — SMALL tier only")
        else:
            allow = False
            allow_normal = False
            allow_small = False
            shadow_mode = True
            if tier == "low":
                reasons.append("Low-liquidity window — shadow only")
            if kz == "none":
                reasons.append("Outside ICT killzone — shadow only")
    elif session_mode == "extended":
        # 24h trading — London/NY full; Asian + off-session SMALL only (FX)
        if kz in ("london", "newyork"):
            allow = True
            allow_normal = True
            allow_small = True
        elif kz == "asian":
            allow = True
            allow_normal = False
            allow_small = True
            reasons.append("Asian session — SMALL tier only")
        else:
            allow = True
            allow_normal = False
            allow_small = True
            reasons.append("Off-session — SMALL tier only (extended 24h)")
    elif session_mode == "24h":
        # V11 — all systems 24/5: scalp + intraday + swing + SMALL + NORMAL
        allow = True
        allow_normal = getattr(s, "allow_24h_normal_trades", True)
        allow_small = getattr(s, "allow_24h_small_trades", True)
        shadow_mode = False
        reasons.append(
            f"24h all-systems — kz={kz or 'off'} "
            f"(scalp/intraday/swing + all tiers)"
        )
    else:
        allow = True

    if getattr(s, "phase5_scheduler_adaptive", True):
        sched = interval
    else:
        sched = int(s.scheduler_interval_minutes)

    return {
        "enabled": True,
        "session_filter_mode": session_mode,
        "liquidity": tier,
        "active_killzone": kz,
        "allow_new_trades": allow,
        "allow_normal_trades": allow_normal,
        "allow_small_trades": allow_small,
        "allow_scalping": getattr(s, "allow_24h_scalping", True) if _is_24h(s) else (kz in ("london", "newyork", "asian") or session_mode == "extended"),
        "allow_intraday": getattr(s, "allow_24h_intraday", True) if _is_24h(s) else kz in ("london", "newyork"),
        "allow_swing": getattr(s, "allow_24h_swing", True) if _is_24h(s) else kz in ("london", "newyork"),
        "run_24h_all_systems": _is_24h(s),
        "shadow_mode": shadow_mode,
        "scheduler_interval_minutes": sched,
        "sl_atr_mult": sl_mult,
        "tp_rr_ratio": tp_rr,
        "utc_hour": now.hour,
        "killzones_utc": KILLZONES_UTC,
        "reason": "; ".join(reasons) if reasons else f"Active session ({tier}, {kz or 'shoulder'})",
    }


def get_scheduler_interval_minutes(settings=None) -> int:
    return int(get_profile(settings)["scheduler_interval_minutes"])
