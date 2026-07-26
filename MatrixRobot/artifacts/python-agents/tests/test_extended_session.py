"""Tests for extended 24h session mode."""
from __future__ import annotations

from tools.session_engine import check_symbol_session_allowed, get_profile


class _ExtendedSettings:
    phase5_intraday_enabled = True
    phase5_session_require_killzone = False
    phase5_block_low_liquidity = False
    phase5_scheduler_adaptive = True
    phase5_scheduler_high_liq_minutes = 30
    phase5_scheduler_medium_liq_minutes = 45
    phase5_scheduler_low_liq_minutes = 30
    session_filter_mode = "extended"
    tiered_block_metals_outside_kz = True
    tiered_block_oil_outside_kz = True
    tiered_block_indices_outside_kz = True
    off_session_min_strength = 0.72
    smart_watcher_enabled = False
    phase5_sl_atr_mult_high = 1.0
    phase5_sl_atr_mult_medium = 1.25
    phase5_sl_atr_mult_low = 1.5
    phase5_tp_rr_high = 1.5
    phase5_tp_rr_medium = 1.75
    phase5_tp_rr_low = 2.0
    scheduler_interval_minutes = 90


def test_extended_off_session_allows_small_fx():
    import tools.session_engine as mod
    orig = mod._active_killzone
    mod._active_killzone = lambda _now=None: "none"
    try:
        p = get_profile(_ExtendedSettings())
        assert p["allow_new_trades"] is True
        assert p["allow_normal_trades"] is False
        assert p["allow_small_trades"] is True
        assert p["shadow_mode"] is False
        ok, reason, shadow = check_symbol_session_allowed("EURUSD", "SMALL", p, _ExtendedSettings())
        assert ok is True
        assert shadow is False
    finally:
        mod._active_killzone = orig


def test_extended_off_session_blocks_indices():
    import tools.session_engine as mod
    orig = mod._active_killzone
    mod._active_killzone = lambda _now=None: "none"
    try:
        p = get_profile(_ExtendedSettings())
        ok, reason, shadow = check_symbol_session_allowed("US30", "SMALL", p, _ExtendedSettings())
        assert ok is False
        assert "indices" in reason.lower() or "off-session" in reason.lower()
    finally:
        mod._active_killzone = orig


def test_rl_policy_updates_q():
    from ml.rl.policy import RLPolicy

    p = RLPolicy(learning_rate=0.5, min_samples=1)
    r1 = p.record_outcome("EURUSD", "BUY", 25.0)
    assert r1["q_value"] > 0
    r2 = p.record_outcome("EURUSD", "BUY", -30.0)
    assert isinstance(r2["q_value"], float)
