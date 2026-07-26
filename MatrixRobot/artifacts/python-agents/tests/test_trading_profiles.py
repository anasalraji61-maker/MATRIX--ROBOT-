"""Tests for trading style profiles."""
from tools.trading_profiles import apply_trading_profile


class _S:
    trading_profile = "conservative"
    symbols = ""
    smart_watcher_enabled = True
    session_filter_mode = "extended"
    primary_timeframe = "H1"
    normal_trade_min_strength = 0.68
    scheduler_interval_minutes = 30


def test_aggressive_profile():
    s = _S()
    s.trading_profile = "aggressive"
    apply_trading_profile(s)
    assert s.smart_watcher_enabled is False
    assert s.session_filter_mode == "off"
    assert s.primary_timeframe == "H1"
    assert "EURUSD" in s.symbols
    assert s.normal_trade_min_strength == 0.58
    assert s.scheduler_interval_minutes == 12


def test_scalp_profile():
    s = _S()
    s.trading_profile = "scalp"
    apply_trading_profile(s)
    assert s.primary_timeframe == "M5"
    assert s.scheduler_interval_minutes == 8
