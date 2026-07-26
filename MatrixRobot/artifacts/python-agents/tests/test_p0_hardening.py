"""P0/P1 hardening tests from ChatGPT full review."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from tools.symbol_specs import pip_size_for, get_spec
from tools import prop_rules, account_state, memory, emergency_guard
from tools.twelve_data import reset_data_meta, get_data_meta, _clear_bars_mock


class _Settings:
    account_profile = "FN_CHALLENGE"
    prop_news_strict_funded = True
    economic_calendar_enabled = True
    active_allow_native_mt5 = False
    active_require_persistent_state = True
    mt5_bridge_url = "http://127.0.0.1:5555"
    mt5_bridge_secret = "test"
    has_mt5 = False
    active_verify_sltp_after_open = True
    phase5_session_require_killzone = True
    max_concurrent_positions = 5
    max_trades_per_day = 30
    min_conviction_threshold = 0.6
    sizing_safety_buffer_pct = 0.3
    max_total_open_risk_pct = 3.0
    require_stop_loss = True
    real_micro_equity_threshold = 100.0
    real_micro_max_risk_per_trade_pct = 3.5
    real_micro_strength_floor_for_sizing = 0.8
    enable_small_trades = True
    small_trade_min_strength = 0.6
    normal_trade_min_strength = 0.68
    small_trade_max_risk_pct = 0.25
    small_trade_max_per_day = 12
    small_trade_max_open = 4
    small_trade_require_rr_min = 1.2
    normal_trade_require_rr_min = 1.5


@pytest.mark.parametrize("symbol,expected_pip", [
    ("EURUSD", 0.0001),
    ("XAUUSD", 0.10),
    ("US30", 1.0),
    ("US500", 0.01),
    ("USTEC", 0.01),
])
def test_index_pip_sizes(symbol, expected_pip):
    assert pip_size_for(symbol) == expected_pip


def test_us500_sizing_not_fx_fallback():
    spec = get_spec("US500")
    assert spec.asset_class == "index"
    assert spec.pip_size == 0.01
    assert spec.pip_value > 0


def test_news_challenge_warning_only():
    state = {"economic_calendar": {"in_blackout": True, "blackout_reason": "NFP", "affected_currencies": ["USD"]}}
    blocked, _ = prop_rules.check_news_blackout(state, _Settings(), "FN_CHALLENGE", False)
    assert blocked is False


def test_news_funded_blocks():
    state = {"economic_calendar": {"in_blackout": True, "blackout_reason": "NFP", "affected_currencies": ["USD"]}}
    blocked, reason = prop_rules.check_news_blackout(state, _Settings(), "FN_FUNDED", True)
    assert blocked is True
    assert "Funded" in reason or "blocked" in reason.lower()


def test_news_real_blocks():
    state = {"economic_calendar": {"in_blackout": True, "blackout_reason": "NFP", "affected_currencies": ["USD"]}}
    blocked, _ = prop_rules.check_news_blackout(state, _Settings(), "REAL", False)
    assert blocked is True


def test_reset_data_meta_clears_mock_lists():
    reset_data_meta()
    meta = get_data_meta()
    assert meta["quotes_mock_symbols"] == []
    assert meta["bars_mock_symbols"] == []


def test_clear_bars_mock_on_success():
    reset_data_meta()
    from tools import twelve_data
    twelve_data._last_meta["bars_mock_symbols"] = ["EURUSD"]
    _clear_bars_mock("EURUSD")
    assert "EURUSD" not in get_data_meta()["bars_mock_symbols"]


@pytest.mark.asyncio
async def test_emergency_close_uses_ticket_key():
    settings = MagicMock()
    settings.mt5_bridge_url = "http://127.0.0.1:5555"
    settings.mt5_bridge_secret = "secret"

    captured = {}

    class _Resp:
        def raise_for_status(self):
            pass

        def json(self):
            return {"success": True}

    class _Client:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            pass

        async def post(self, url, headers=None, json=None):
            captured["json"] = json
            return _Resp()

    with patch("tools.emergency_guard.httpx.AsyncClient", return_value=_Client()):
        res = await emergency_guard._close_position_via_bridge(settings, 12345)
    assert res["success"] is True
    assert captured["json"]["ticket"] == 12345


@pytest.mark.asyncio
async def test_bridge_unreachable_no_native_fallback():
    from tools.mt5_bridge import open_trade

    settings = _Settings()
    with patch("tools.mt5_bridge.get_settings", return_value=settings):
        with patch("tools.mt5_bridge._http_open", side_effect=ConnectionError("down")):
            result = await open_trade(
                "EURUSD", "BUY", 0.01, 1.08, 1.09, "ACTIVE",
                bridge_url="http://127.0.0.1:5555",
            )
    assert result.executed is False
    assert "native fallback disabled" in result.message.lower()


@pytest.mark.asyncio
async def test_active_preflight_requires_persistent_state():
    from tools import circuit_status

    settings = _Settings()
    with patch("tools.circuit_status.get_settings", return_value=settings):
        with patch("tools.circuit_status._bridge_block_reason", return_value=(False, "", {"required": False})):
            with patch("tools.circuit_status.emergency_guard.get_lockout", return_value={}):
                with patch("tools.circuit_status.memory.has_persistent_backend", return_value=False):
                    pre = await circuit_status.preflight_cycle("ACTIVE")
    assert pre["can_run"] is False
    assert pre["reason"] == "no_persistent_state"


def test_reset_for_new_challenge_clears_keys():
    memory.store("prop_qualified_trades_count", 5)
    memory.store("small_trades_today", 3)
    memory.store("open_positions", [{"symbol": "EURUSD"}])
    memory._store["prop_qualified_trades_count__secondary"] = "2"
    emergency_guard.set_daily_lockout("test", 4.0, -100.0)

    account_state.reset_for_new_challenge()

    assert memory.retrieve("prop_qualified_trades_count") is None
    assert memory.retrieve("small_trades_today") is None
    assert memory.retrieve("open_positions") is None
    assert memory.retrieve("prop_qualified_trades_count__secondary") is None
    assert emergency_guard.get_lockout() == {}


@pytest.mark.asyncio
async def test_secondary_no_quote_fallback_in_active():
    from agents import execution_agent as ex

    account = MagicMock()
    account.id = "secondary"
    account.bridge_url = "http://127.0.0.1:5556"
    account.risk_per_trade_pct = 0.8
    account.max_daily_drawdown_pct = 4.0
    account.max_total_drawdown_pct = 9.0
    account.account_profile = "FN_FUNDED"
    account.max_concurrent_positions = 5
    account.max_trades_per_day = 30
    account.min_conviction_threshold = 0.6
    account.starting_balance = 10000
    account.allows_symbol = lambda s: True

    state = {
        "market_data": {"quotes": []},
        "indicators": {"EURUSD": {"atr_14": 0.001}},
        "approved_risk_trades": [],
    }
    settings = _Settings()
    settings.max_concurrent_positions = 5
    settings.max_trades_per_day = 30

    with patch.object(ex.account_state, "sync_open_positions", new=AsyncMock(return_value=[])):
        with patch.object(ex.account_state, "refresh_account", new=AsyncMock(return_value={
            "equity": 10000, "starting_balance": 10000,
            "daily_drawdown_pct": 0, "total_drawdown_pct": 0,
        })):
            with patch.object(ex.account_state, "trades_today_count", return_value=0):
                with patch.object(ex.memory, "retrieve", return_value=[]):
                    out = await ex._run_for_account(
                        account, [{"symbol": "EURUSD", "signal": "BUY", "strength": 0.75}],
                        state, "ACTIVE", settings,
                    )
    assert out[0]["executed"] is False
    assert "live quote" in out[0]["message"].lower()
