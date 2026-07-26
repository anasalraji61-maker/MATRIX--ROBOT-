"""Tests for NORMAL / SMALL / HOLD trade tier classification."""
from tools.trade_tiers import classify_trade_tier, min_candidate_strength, risk_pct_for_tier


class _Settings:
    enable_small_trades = True
    small_trade_min_strength = 0.60
    normal_trade_min_strength = 0.72
    min_conviction_threshold = 0.60
    max_risk_per_trade_pct = 0.8
    small_trade_max_risk_pct = 0.25


def test_hold_below_small_min():
    s = _Settings()
    assert classify_trade_tier(0.55, s) == "HOLD"


def test_small_tier_mid_range():
    s = _Settings()
    assert classify_trade_tier(0.65, s) == "SMALL"


def test_normal_tier_high_strength():
    s = _Settings()
    assert classify_trade_tier(0.75, s) == "NORMAL"


def test_small_disabled_requires_normal_min():
    s = _Settings()
    s.enable_small_trades = False
    assert classify_trade_tier(0.65, s) == "HOLD"
    assert min_candidate_strength(s) == 0.72


def test_risk_pct_for_tiers():
    s = _Settings()
    assert risk_pct_for_tier("NORMAL", s) == 0.8
    assert risk_pct_for_tier("SMALL", s) == 0.25
