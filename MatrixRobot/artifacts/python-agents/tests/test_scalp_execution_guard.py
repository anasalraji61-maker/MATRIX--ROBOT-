"""Scalp execution guard tests — V10 protections on bypass path."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from tools.scalp_execution_guard import preflight_batch, preflight_trade


@pytest.mark.asyncio
async def test_preflight_batch_blocks_daily_lockout():
    state = {"prop_status": {"can_trade": True}, "risk": {}}
    with patch("tools.scalp_execution_guard.is_daily_locked", return_value=True):
        ok, reason = await preflight_batch(state, "ACTIVE")
    assert ok is False
    assert "lockout" in reason.lower()


@pytest.mark.asyncio
async def test_preflight_batch_blocks_manual_check():
    state = {"prop_status": {"can_trade": True}, "risk": {}}
    with patch("tools.scalp_execution_guard.is_daily_locked", return_value=False):
        with patch("tools.bridge_manual.is_blocking", return_value=True):
            ok, reason = await preflight_batch(state, "ACTIVE")
    assert ok is False
    assert "manual" in reason.lower()


def test_preflight_trade_blocks_correlation():
    state = {
        "market_data": {"quotes": [{"symbol": "EURUSD", "bid": 1.08, "ask": 1.08002}]},
        "mode": "ACTIVE",
    }
    candidate = {
        "symbol": "EURUSD",
        "signal": "BUY",
        "sizing": {"sl_pips": 5, "tp_pips": 7},
    }
    existing = [{"symbol": "GBPUSD", "action": "BUY"}]

    class _S:
        correlation_guard_enabled = True
        scalping_max_open_trades = 2
        max_concurrent_positions = 7
        max_trades_per_day = 30
        require_stop_loss = True
        phase5_liquidity_guard_enabled = True
        phase5_intraday_enabled = True
        phase5_max_spread_pips_fx = 3.0
        max_same_currency_exposure = 3
        max_correlated_trades = 2

    with patch("tools.scalp_execution_guard.correlation.is_blocked", return_value=(True, "correlation blocked")):
        with patch("tools.scalp_execution_guard.symbol_quarantine_reason", return_value=""):
            with patch("tools.scalp_execution_guard.check_spread", return_value=(True, "")):
                ok, reason = preflight_trade(candidate, state, "ACTIVE", existing, _S())
    assert ok is False
    assert "correlation" in reason


def test_full_power_demo_enforces_on_demo_broker():
    from config import Settings
    from tools.trading_mode_profiles import apply_trading_mode_profile

    s = Settings(
        trading_mode_profile="FULL_POWER_DEMO",
        mt5_server="MetaQuotes-Demo",
    )
    apply_trading_mode_profile(s)
    assert s.scalping_mode == "enforce"
    assert s.council_mode == "enforce"


def test_full_power_demo_shadow_on_live():
    from config import Settings
    from tools.trading_mode_profiles import apply_trading_mode_profile

    s = Settings(
        trading_mode_profile="FULL_POWER_DEMO",
        mt5_server="ICMarkets-Live",
        account_profile="REAL",
        scalping_mode="enforce",
        council_mode="enforce",
    )
    apply_trading_mode_profile(s)
    assert s.scalping_mode == "shadow"
    assert s.council_mode == "advisory"
