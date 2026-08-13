"""24h all-systems mode tests."""
from __future__ import annotations

from config import Settings
from tools.trading_mode_profiles import apply_trading_mode_profile
from tools.session_24h import is_24h_all_systems
from tools.session_engine import check_symbol_session_allowed, get_profile
from tools.strategy_router import route_market_mode


def test_full_power_enables_24h_all_systems():
    s = Settings(trading_mode_profile="FULL_POWER_DEMO", mt5_server="MetaQuotes-Demo")
    apply_trading_mode_profile(s)
    assert s.session_filter_mode == "24h"
    assert is_24h_all_systems(s)
    assert s.run_24h_all_systems is True


def test_24h_allows_normal_off_session():
    s = Settings(
        session_filter_mode="24h",
        run_24h_all_systems=True,
        allow_24h_normal_trades=True,
        tiered_block_indices_outside_kz=True,
    )
    profile = {
        "enabled": True,
        "active_killzone": "none",
        "liquidity": "low",
        "allow_new_trades": True,
        "allow_normal_trades": True,
        "allow_small_trades": True,
    }
    ok, reason, shadow = check_symbol_session_allowed("EURUSD", "NORMAL", profile, s)
    assert ok is True
    assert shadow is False
    assert reason == ""


def test_24h_router_all_systems_active():
    s = Settings(
        session_filter_mode="24h",
        run_24h_all_systems=True,
        allow_24h_scalping=True,
        allow_24h_intraday=True,
        allow_24h_swing=True,
    )
    profile = get_profile(s)
    route = route_market_mode(s, profile)
    assert route["run_24h_all_systems"] is True
    assert route["scalping_allowed"] is True
    assert route["intraday_allowed"] is True
    assert route["swing_allowed"] is True


def test_24h_profile_session_flags():
    s = Settings(trading_mode_profile="FULL_POWER_DEMO", mt5_server="MetaQuotes-Demo")
    apply_trading_mode_profile(s)
    profile = get_profile(s)
    assert profile.get("run_24h_all_systems") is True
    assert profile.get("allow_scalping") is True
    assert profile.get("allow_intraday") is True
    assert profile.get("allow_swing") is True
    assert profile.get("shadow_mode") is False
