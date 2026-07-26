"""Phase 6 hardening tests."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest

from tools.prop_time import prop_server_today, seconds_until_prop_server_midnight
from tools.data_quality import validate_active_data
from tools.position_manager import _new_sl_tp


class _Settings:
    prop_server_utc_offset_hours = 3
    active_fail_closed_data = True
    active_require_live_news = True
    active_fail_closed_no_account = True
    phase5_trail_lock_r = 0.5


def test_prop_server_today_format():
    with patch("tools.prop_time.get_settings", return_value=_Settings()):
        today = prop_server_today()
        assert len(today) == 10
        assert today[4] == "-" and today[7] == "-"


def test_seconds_until_prop_server_midnight_positive():
    with patch("tools.prop_time.get_settings", return_value=_Settings()):
        assert seconds_until_prop_server_midnight() >= 60


def test_active_blocks_mock_news():
    state = {
        "market_data": {"news_source": "mock", "data_quality": {}},
        "account": {"available": True},
    }
    ok, reason = validate_active_data(state, "ACTIVE")
    assert ok is False
    assert "news" in reason.lower()


def test_active_blocks_mock_quotes():
    """Per-symbol quarantine: one mock quote must not block the whole cycle."""
    from tools.data_quality import compute_data_quarantine

    state = {
        "symbols_analyzed": ["EURUSD", "GBPUSD", "USDJPY"],
        "market_data": {
            "news_source": "polygon",
            "data_quality": {
                "quotes_source": "twelve_data",
                "quotes_mock_symbols": ["EURUSD"],
                "bars_mock_symbols": [],
            },
        },
        "account": {"available": True},
    }

    class _Quarantine:
        active_fail_closed_data = True
        active_require_live_news = True
        active_fail_closed_no_account = True
        active_data_per_symbol_quarantine = True
        active_data_global_block_ratio = 0.5
        active_disabled_symbols = ""
        symbol_list = ["EURUSD", "GBPUSD", "USDJPY"]

        @property
        def active_disabled_symbol_set(self):
            return set()

    with patch("tools.data_quality.get_settings", return_value=_Quarantine()):
        snap = compute_data_quarantine(state, "ACTIVE")
        ok, reason = validate_active_data({**state, "data_quarantine": snap}, "ACTIVE")
    assert snap["global_data_block"] is False
    assert "EURUSD" in snap["data_quarantine_symbols"]
    assert ok is True
    assert reason == ""


def test_active_blocks_mock_quotes_legacy_mode():
    """When per-symbol quarantine is off, single mock quote still blocks globally."""
    state = {
        "market_data": {
            "news_source": "polygon",
            "data_quality": {"quotes_mock_symbols": ["EURUSD"], "bars_mock_symbols": []},
        },
        "account": {"available": True},
    }

    class _Legacy:
        active_fail_closed_data = True
        active_require_live_news = True
        active_fail_closed_no_account = True
        active_data_per_symbol_quarantine = False
        active_data_global_block_ratio = 0.5
        active_disabled_symbols = ""
        symbol_list = ["EURUSD"]

        @property
        def active_disabled_symbol_set(self):
            return set()

    with patch("tools.data_quality.get_settings", return_value=_Legacy()):
        ok, reason = validate_active_data(state, "ACTIVE")
    assert ok is False
    assert "EURUSD" in reason


def test_paper_allows_mock():
    state = {"market_data": {"news_source": "mock"}, "account": {"available": False}}
    ok, _ = validate_active_data(state, "PAPER_MODE")
    assert ok is True


def test_sell_trailing_moves_sl_down():
    pos = {
        "symbol": "EURUSD",
        "action": "SELL",
        "entry_price": 1.1000,
        "stop_loss": 1.1050,
        "initial_stop_loss": 1.1050,
        "take_profit": 1.0900,
    }
    new_sl, _ = _new_sl_tp(pos, 1.0950, _Settings(), breakeven=False, trail=True)
    assert new_sl is not None
    assert new_sl < 1.1050
