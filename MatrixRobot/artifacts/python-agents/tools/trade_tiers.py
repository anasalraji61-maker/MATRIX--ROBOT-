"""Trade sizing tiers — same brain quality, different risk budgets.

NORMAL : strength >= normal_trade_min_strength — full risk cap
SMALL  : strength in [small_trade_min, normal) — reduced risk cap
HOLD   : below small_trade_min_strength
"""
from __future__ import annotations

from config import get_settings


def classify_trade_tier(strength: float, settings=None) -> str:
    s = settings or get_settings()
    st = float(strength or 0.0)
    if st < float(s.small_trade_min_strength):
        return "HOLD"
    if st >= float(s.normal_trade_min_strength):
        return "NORMAL"
    if getattr(s, "enable_small_trades", False):
        return "SMALL"
    return "HOLD"


def min_candidate_strength(settings=None) -> float:
    """Lowest strength that may reach execution (still filtered by tier)."""
    s = settings or get_settings()
    if getattr(s, "enable_small_trades", False):
        return float(s.small_trade_min_strength)
    return max(float(s.min_conviction_threshold), float(s.normal_trade_min_strength))


def risk_pct_for_tier(tier: str, settings=None) -> float | None:
    s = settings or get_settings()
    if tier == "NORMAL":
        return float(s.max_risk_per_trade_pct)
    if tier == "SMALL":
        return float(s.small_trade_max_risk_pct)
    return None


def rr_minimum_for_tier(tier: str, settings=None) -> float:
    s = settings or get_settings()
    if tier == "SMALL":
        return float(s.small_trade_require_rr_min)
    return float(s.normal_trade_require_rr_min)


def tier_label(tier: str) -> str:
    return {"NORMAL": "normal", "SMALL": "small", "HOLD": "hold"}.get(tier, tier.lower())
