"""ChatGPT surgical filters — quarantine, CHF gates, time window, XAGUSD."""
from __future__ import annotations

from config import get_settings
from tools.prop_time import prop_server_now


_CHF_EXEMPT = frozenset({"AUDCHF", "NZDCHF"})


def symbol_quarantine_set(settings=None) -> set[str]:
    s = settings or get_settings()
    raw = str(getattr(s, "symbol_quarantine", "") or "").strip()
    if not raw:
        return set()
    return {x.strip().upper() for x in raw.split(",") if x.strip()}


def is_symbol_quarantined(symbol: str, settings=None) -> tuple[bool, str]:
    sym = (symbol or "").upper()
    if sym in symbol_quarantine_set(settings):
        return True, f"symbol quarantine (48h review): {sym}"
    return False, ""


def is_chf_pair(symbol: str) -> bool:
    sym = (symbol or "").upper()
    return "CHF" in sym and sym not in _CHF_EXEMPT


def time_window_bonuses(settings=None) -> tuple[float, float]:
    """Extra min strength / RR during 09:00–12:00 server time."""
    s = settings or get_settings()
    hour = prop_server_now().hour
    if 9 <= hour < 12:
        return (
            float(getattr(s, "time_filter_09_12_min_strength_bonus", 0.0)),
            float(getattr(s, "time_filter_09_12_min_rr_bonus", 0.0)),
        )
    return 0.0, 0.0


def effective_scalp_thresholds(settings=None) -> tuple[float, float]:
    s = settings or get_settings()
    min_strength = float(s.scalping_min_strength)
    min_rr = float(s.scalping_min_rr)
    sb, rb = time_window_bonuses(s)
    return min_strength + sb, min_rr + rb


def check_entry_gates(
    symbol: str,
    strength: float,
    rr: float,
    *,
    settings=None,
    trade_tier: str = "INTRADAY",
) -> tuple[bool, str]:
    """Unified surgical entry check — does not block on missing data."""
    s = settings or get_settings()
    sym = (symbol or "").upper()

    blocked, reason = is_symbol_quarantined(sym, s)
    if blocked:
        return False, reason

    str_bonus, rr_bonus = time_window_bonuses(s)
    min_strength = float(s.scalping_min_strength) if trade_tier == "SCALP" else float(
        getattr(s, "normal_trade_min_strength", 0.68)
    )
    min_rr = float(s.scalping_min_rr) if trade_tier == "SCALP" else float(
        getattr(s, "normal_trade_require_rr_min", 1.2)
    )
    min_strength += str_bonus
    min_rr += rr_bonus

    if is_chf_pair(sym):
        chf_str = float(getattr(s, "chf_pairs_min_strength", 0) or 0)
        chf_rr = float(getattr(s, "chf_pairs_min_rr", 0) or 0)
        if chf_str > 0:
            min_strength = max(min_strength, chf_str)
        if chf_rr > 0:
            min_rr = max(min_rr, chf_rr)

    if strength < min_strength:
        return False, f"surgical gate: strength {strength:.2f} < {min_strength:.2f}"
    if rr < min_rr:
        return False, f"surgical gate: RR {rr:.2f} < {min_rr:.2f}"
    return True, ""


def xagusd_risk_multiplier(symbol: str, settings=None) -> float:
    s = settings or get_settings()
    if (symbol or "").upper() != "XAGUSD":
        return 1.0
    return float(getattr(s, "xagusd_risk_multiplier", 1.0) or 1.0)


def xagusd_breakeven_required(symbol: str, settings=None) -> bool:
    s = settings or get_settings()
    if (symbol or "").upper() != "XAGUSD":
        return False
    return bool(getattr(s, "xagusd_require_breakeven", False))
