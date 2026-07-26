"""V11 Strategy Router — scalp vs intraday vs swing; 24h all-systems support."""
from __future__ import annotations

from typing import Any

from tools.session_24h import is_24h_all_systems
from tools.session_engine import get_profile


def route_market_mode(settings=None, session_profile: dict | None = None) -> dict[str, Any]:
    """Session-aware routing for which trading systems may run."""
    from config import get_settings

    s = settings or get_settings()
    profile = session_profile or get_profile(s)
    kz = profile.get("active_killzone", "none")
    liquidity = profile.get("liquidity", "low")

    if is_24h_all_systems(s):
        news_blocked = bool(profile.get("news_blackout", False))
        scalp = getattr(s, "allow_24h_scalping", True) and not news_blocked
        intraday = getattr(s, "allow_24h_intraday", True) and not news_blocked
        swing = getattr(s, "allow_24h_swing", True) and not news_blocked
        reason = f"24h all-systems — scalp={scalp} intraday={intraday} swing={swing} kz={kz}"
        if news_blocked:
            reason += "; news blackout"
        primary = "scalping" if scalp else ("intraday" if intraday else ("swing" if swing else "no_trade"))
        return {
            "primary_mode": primary,
            "scalping_allowed": scalp,
            "intraday_allowed": intraday,
            "swing_allowed": swing,
            "active_killzone": kz,
            "liquidity": liquidity,
            "news_blackout": news_blocked,
            "run_24h_all_systems": True,
            "reason": reason,
        }

    scalp = False
    intraday = False
    swing = False
    reason_parts: list[str] = []

    if kz in ("london", "newyork"):
        scalp = intraday = swing = True
        reason_parts.append("London/NY — full + intraday + scalping")
    elif kz == "asian":
        scalp = True
        intraday = True
        reason_parts.append("Asian — scalping + intraday/range")
    elif liquidity == "low":
        scalp = True
        reason_parts.append("Off-session — scalping active")
    else:
        scalp = True
        reason_parts.append("Medium liquidity — scalping + intraday")
        intraday = True

    news_blocked = bool(profile.get("news_blackout", False))
    if news_blocked:
        scalp = intraday = swing = False
        reason_parts.append("News window — no new trades")

    mode = "no_trade"
    if scalp:
        mode = "scalping"
    elif intraday:
        mode = "intraday"
    elif swing:
        mode = "swing"

    return {
        "primary_mode": mode,
        "scalping_allowed": scalp,
        "intraday_allowed": intraday,
        "swing_allowed": swing,
        "active_killzone": kz,
        "liquidity": liquidity,
        "news_blackout": news_blocked,
        "run_24h_all_systems": False,
        "reason": "; ".join(reason_parts),
    }


def candidate_allowed(candidate: dict, route: dict) -> tuple[bool, str]:
    """Filter a candidate against router (scalp/intraday/swing)."""
    style = str(
        candidate.get("trade_style")
        or candidate.get("strategy")
        or candidate.get("strategy_name")
        or ""
    ).lower()

    if "swing" in style and not route.get("swing_allowed"):
        return False, "swing not allowed in current session"
    if "intraday" in style and not route.get("intraday_allowed"):
        return False, "intraday not allowed in current session"
    if not route.get("scalping_allowed") and ("scalp" in style or route.get("primary_mode") == "scalping"):
        if "scalp" in style or float(candidate.get("strength") or 0) < 0.7:
            return False, route.get("reason", "scalping not allowed")

    strength = float(candidate.get("strength") or 0)
    if strength < 0.5:
        return False, "strength too low for router"
    return True, ""
