"""Tests for Phase 5 session engine."""
from __future__ import annotations

from tools.session_engine import get_profile, _liquidity_tier


class _Settings:
    phase5_intraday_enabled = True
    phase5_session_require_killzone = True
    phase5_block_low_liquidity = True
    phase5_scheduler_adaptive = True
    phase5_scheduler_high_liq_minutes = 20
    phase5_scheduler_medium_liq_minutes = 60
    phase5_scheduler_low_liq_minutes = 90
    session_filter_mode = "tiered"
    tiered_block_metals_outside_kz = True
    tiered_block_indices_outside_kz = True
    phase5_sl_atr_mult_high = 1.0
    phase5_sl_atr_mult_medium = 1.25
    phase5_sl_atr_mult_low = 1.5
    phase5_tp_rr_high = 1.5
    phase5_tp_rr_medium = 1.75
    phase5_tp_rr_low = 2.0
    scheduler_interval_minutes = 90


def test_liquidity_tier_high_for_london():
    assert _liquidity_tier("london") == "high"
    assert _liquidity_tier("newyork") == "high"


def test_profile_blocks_outside_killzone_tiered():
    from tools import session_engine as mod
    orig = mod._active_killzone
    mod._active_killzone = lambda _now=None: "none"
    try:
        p = get_profile(_Settings())
        assert p["allow_new_trades"] is False
        assert p["shadow_mode"] is True
        assert p["liquidity"] == "low"
    finally:
        mod._active_killzone = orig


def test_profile_allows_london_with_tighter_tp():
    monkeypatch = None
    from tools import session_engine as se
    import tools.session_engine as mod
    orig = mod._active_killzone
    mod._active_killzone = lambda _now=None: "london"
    try:
        p = get_profile(_Settings())
        assert p["allow_new_trades"] is True
        assert p["liquidity"] == "high"
        assert p["tp_rr_ratio"] == 1.5
        assert p["scheduler_interval_minutes"] == 20
    finally:
        mod._active_killzone = orig
