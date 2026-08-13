"""Tests for per-symbol data quarantine and tiered session filter."""
from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from tools.data_quality import compute_data_quarantine, validate_active_data, symbol_quarantine_reason
from tools.session_engine import check_symbol_session_allowed, get_profile


class _Settings:
    active_fail_closed_data = True
    active_require_live_news = True
    active_fail_closed_no_account = True
    active_data_per_symbol_quarantine = True
    active_data_global_block_ratio = 0.5
    active_disabled_symbols = "US30,US500,USTEC,XAUUSD,XAGUSD"
    session_filter_mode = "tiered"
    tiered_block_metals_outside_kz = True
    tiered_block_indices_outside_kz = True
    phase5_session_require_killzone = True
    phase5_block_low_liquidity = True
    symbols = "EURUSD,US30"
    enable_small_trades = True
    small_trade_min_strength = 0.60
    normal_trade_min_strength = 0.68
    min_conviction_threshold = 0.60
    max_concurrent_positions = 7
    small_trade_max_open = 4
    small_trade_max_per_day = 12
    small_trade_max_risk_pct = 0.25
    small_trade_require_rr_min = 1.2
    normal_trade_require_rr_min = 1.5
    max_risk_per_trade_pct = 0.8
    correlation_guard_enabled = False
    economic_calendar_enabled = False
    volatility_regime_enabled = False
    account_profile = "FN_CHALLENGE"

    @property
    def symbol_list(self):
        return ["EURUSD", "US30"]

    @property
    def active_disabled_symbol_set(self):
        return {s.strip().upper() for s in self.active_disabled_symbols.split(",") if s.strip()}


def test_single_mock_symbol_does_not_global_block():
    state = {
        "symbols_analyzed": ["EURUSD", "NZDUSD", "US30"],
        "market_data": {
            "news_source": "polygon",
            "data_quality": {
                "quotes_source": "twelve_data",
                "quotes_mock_symbols": ["US30"],
                "bars_mock_symbols": [],
            },
        },
        "account": {"available": True},
    }
    snap = compute_data_quarantine(state, "ACTIVE")
    assert snap["global_data_block"] is False
    assert "US30" in snap["data_quarantine_symbols"]
    assert "EURUSD" not in snap["data_quarantine_symbols"]

    ok, reason = validate_active_data({**state, "data_quarantine": snap}, "ACTIVE")
    assert ok is True
    assert reason == ""


def test_majority_stale_triggers_global_block():
    state = {
        "symbols_analyzed": ["EURUSD", "GBPUSD", "US30", "US500"],
        "market_data": {
            "news_source": "polygon",
            "data_quality": {
                "quotes_source": "twelve_data",
                "quotes_mock_symbols": ["EURUSD", "GBPUSD", "US30"],
                "bars_mock_symbols": ["US500"],
            },
        },
        "account": {"available": True},
    }
    snap = compute_data_quarantine(state, "ACTIVE")
    assert snap["global_data_block"] is True


def test_active_disabled_symbol_quarantined():
    state = {"symbols_analyzed": ["EURUSD"], "market_data": {"data_quality": {}}}
    with patch("tools.data_quality.get_settings", return_value=_Settings()):
        reason = symbol_quarantine_reason("XAUUSD", state, "ACTIVE")
    assert "disabled" in reason.lower()


def test_tiered_london_allows_normal():
    profile = {
        "enabled": True,
        "active_killzone": "london",
        "liquidity": "high",
        "allow_new_trades": True,
    }
    ok, reason, shadow = check_symbol_session_allowed("EURUSD", "NORMAL", profile, _Settings())
    assert ok is True
    assert shadow is False


def test_tiered_asian_blocks_normal_allows_small():
    profile = {
        "enabled": True,
        "active_killzone": "asian",
        "liquidity": "medium",
        "allow_new_trades": True,
        "allow_normal_trades": False,
        "allow_small_trades": True,
    }
    ok_n, _, _ = check_symbol_session_allowed("NZDUSD", "NORMAL", profile, _Settings())
    ok_s, _, _ = check_symbol_session_allowed("NZDUSD", "SMALL", profile, _Settings())
    assert ok_n is False
    assert ok_s is True


def test_tiered_off_session_shadow():
    profile = {
        "enabled": True,
        "active_killzone": "none",
        "liquidity": "low",
        "allow_new_trades": False,
        "shadow_mode": True,
        "reason": "Outside ICT killzone — shadow only",
    }
    ok, reason, shadow = check_symbol_session_allowed("NZDUSD", "SMALL", profile, _Settings())
    assert ok is False
    assert shadow is True
    assert "killzone" in reason.lower() or "shadow" in reason.lower()


def test_risk_continues_when_only_us30_stale():
    import asyncio
    from tools.risk_batch import evaluate_candidates

    state = {
        "mode": "ACTIVE",
        "symbols_analyzed": [
            "EURUSD", "GBPUSD", "USDJPY", "USDCHF", "AUDUSD", "NZDUSD", "USDCAD",
            "EURGBP", "EURJPY", "GBPJPY", "EURAUD", "EURCHF", "AUDJPY", "CHFJPY",
            "CADJPY", "NZDJPY", "GBPCHF", "AUDCAD", "AUDNZD", "US30",
        ],
        "session_profile": {
            "enabled": True,
            "session_filter_mode": "tiered",
            "active_killzone": "london",
            "liquidity": "high",
            "allow_new_trades": True,
        },
        "market_data": {
            "news_source": "polygon",
            "data_quality": {
                "quotes_source": "twelve_data",
                "quotes_mock_symbols": ["US30"],
                "bars_mock_symbols": [],
            },
            "quotes": [
                {"symbol": "EURUSD", "bid": 1.08, "ask": 1.0802, "spread_pips": 0.2},
            ],
        },
        "account": {
            "available": True,
            "equity": 10000,
            "starting_balance": 10000,
            "daily_drawdown_pct": 0.0,
            "total_drawdown_pct": 0.0,
        },
        "analyses": [
            {"symbol": "EURUSD", "signal": "BUY", "strength": 0.75},
            {"symbol": "US30", "signal": "SELL", "strength": 0.8},
        ],
        "indicators": {"EURUSD": {"atr_14": 0.001}},
        "economic_calendar": {"affected_currencies": []},
    }

    prop_ok = type("P", (), {"can_trade": True, "block_reason": ""})()

    with patch("tools.position_reconciler.ensure_synced", new=AsyncMock(return_value=True)), \
         patch("tools.prop_rules.evaluate", new=AsyncMock(return_value=prop_ok)), \
         patch("tools.prop_rules.open_risk_pct", return_value=0.0), \
         patch("tools.prop_rules.check_news_blackout", return_value=(False, "")), \
         patch("tools.memory.retrieve", return_value=[]), \
         patch("tools.risk_batch.asdict", return_value={"can_trade": True}), \
         patch("tools.risk_sizing.compute_safe_sizing", return_value={
             "rejected": False,
             "lots": 0.01,
             "sl_pips": 15,
             "tp_pips": 30,
             "risk_usd": 10.0,
             "risk_pct_of_starting": 0.1,
             "rr": 2.0,
             "cap_reason": "per_trade",
         }), \
         patch("tools.liquidity_guard.check_spread", return_value=(True, "")), \
         patch("config.get_settings", return_value=_Settings()):
        result = asyncio.run(evaluate_candidates(state))

    assert "US30" in (result.get("risk_rejection_report") or {}).get("data_quarantined_symbols", {})
    approved_syms = [t["symbol"] for t in result.get("approved_risk_trades") or []]
    assert "US30" not in approved_syms
    assert result.get("risk", {}).get("approved") is True or "EURUSD" in approved_syms or len(approved_syms) > 0
