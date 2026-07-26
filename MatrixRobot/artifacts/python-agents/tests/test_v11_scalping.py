"""V11 Scalping + Trading Council tests."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from tools.cheap_scanner import run_cheap_scan
from tools.scalping_guard import (
    is_demo_account,
    scalping_asset_allowed,
    scalping_effective_enabled,
    scanner_universe,
)
from tools.scalp_strategies import ema_pullback_scalp, evaluate_all
from tools.strategy_router import route_market_mode
from tools.trading_council import evaluate_candidate, meta_judge
from tools.scalp_risk import approve_candidates, compute_scalp_sizing


class _DemoSettings:
    scalping_enabled = True
    scalping_demo_only = True
    scalping_mode = "shadow"
    scalping_allowed_assets = "FX_ONLY"
    scalping_timeframes = "M5,M15"
    scalping_max_trades_per_day = 10
    scalping_max_open_trades = 2
    scalping_risk_multiplier = 0.10
    scalping_min_strength = 0.62
    scalping_min_rr = 1.1
    scalping_max_hold_minutes = 30
    scalping_sl_pips_min = 3.0
    scalping_sl_pips_max = 8.0
    scalping_tp_pips_min = 3.0
    scalping_tp_pips_max = 10.0
    scalping_max_spread_pips_fx = 2.0
    scanner_universe_use_full_registry = True
    cheap_scan_top_deep = 10
    council_top_candidates = 5
    council_enabled = True
    mt5_server = "MetaQuotes-Demo"
    account_profile = "FN_CHALLENGE"
    trading_state = "ACTIVE"
    active_disabled_symbols = "US30,US500,USTEC"
    symbols = "EURUSD,GBPUSD"
    max_risk_per_trade_pct = 0.8
    phase5_liquidity_guard_enabled = True
    phase5_intraday_enabled = True
    phase5_max_spread_pips_fx = 3.0
    phase5_max_spread_pips_xau = 50.0
    phase5_max_spread_pips_index = 30.0
    council_top_n = 8
    phase5_sl_atr_mult_low = 1.5
    phase5_sl_atr_mult_medium = 1.25
    phase5_sl_atr_mult_high = 1.0
    phase5_tp_rr_low = 2.0
    phase5_tp_rr_medium = 1.75
    phase5_tp_rr_high = 1.5
    phase5_intraday_enabled = True

    @property
    def symbol_list(self):
        return ["EURUSD", "GBPUSD"]

    @property
    def active_disabled_symbol_set(self):
        return {"US30", "US500", "USTEC"}


def test_demo_guard_allows_metaquotes_demo():
    assert is_demo_account(_DemoSettings()) is True
    enabled, reason = scalping_effective_enabled("ACTIVE", _DemoSettings())
    assert enabled is True
    assert reason == ""


def test_demo_guard_blocks_real_profile_non_demo_server():
    s = _DemoSettings()
    s.mt5_server = "ICMarkets-Live"
    s.account_profile = "REAL"
    enabled, reason = scalping_effective_enabled("ACTIVE", s)
    assert enabled is False
    assert "demo" in reason.lower()


def test_scalping_fx_only():
    assert scalping_asset_allowed("EURUSD", _DemoSettings()) is True
    assert scalping_asset_allowed("XAUUSD", _DemoSettings()) is False


def test_scanner_universe_excludes_disabled_indices():
    universe = scanner_universe(_DemoSettings())
    assert "US30" not in universe
    assert "EURUSD" in universe
    assert len(universe) >= 48


def test_cheap_scan_ranks_symbols():
    state = {
        "mode": "ACTIVE",
        "indicators": {
            "EURUSD": {
                "rsi_14": 72, "adx_14": 28, "trend": "bullish",
                "macd_hist": 0.002, "stoch_k": 80, "volatility_regime": "high",
            },
            "GBPUSD": {
                "rsi_14": 50, "adx_14": 10, "trend": "neutral",
                "macd_hist": 0, "stoch_k": 50,
            },
        },
        "market_data": {"quotes": [
            {"symbol": "EURUSD", "bid": 1.08, "ask": 1.08002},
            {"symbol": "GBPUSD", "bid": 1.27, "ask": 1.27002},
        ]},
    }
    with patch("tools.cheap_scanner.get_settings", return_value=_DemoSettings()):
        with patch("tools.cheap_scanner.symbol_quarantine_reason", return_value=""):
            with patch("tools.cheap_scanner.scanner_universe", return_value=["EURUSD", "GBPUSD"]):
                result = run_cheap_scan(state)
    assert result["scanned_symbols_count"] == 2
    assert result["cheap_candidates_count"] >= 1
    assert result["top_deep_symbols"][0] == "EURUSD"


def test_ema_pullback_scalp_buy():
    ind = {
        "ema_20": 1.1000, "ema_50": 1.0950, "close": 1.0998,
        "rsi_14": 48,
    }
    hit = ema_pullback_scalp(ind)
    assert hit is not None
    assert hit["signal"] == "BUY"
    assert hit["strategy"] == "ema_pullback_scalp"


def test_strategy_router_london_full():
    route = route_market_mode(_DemoSettings(), {"active_killzone": "london", "liquidity": "high"})
    assert route["scalping_allowed"] is True
    assert route["intraday_allowed"] is True
    assert route["primary_mode"] == "scalping"


def test_council_skeptic_veto():
    state = {
        "indicators": {"EURUSD": {"trend": "bearish", "rsi_14": 55, "adx_14": 20}},
        "mtf": {"EURUSD": {"H1": {"trend": "bearish"}}},
        "volatility_regimes": {"EURUSD": {"regime": "normal"}},
        "ict": {"EURUSD": {}},
        "economic_calendar": {},
        "market_data": {"quotes": [{"symbol": "EURUSD", "bid": 1.08, "ask": 1.08002}]},
        "risk": {"approved": True},
        "prop_status": {"can_trade": True},
        "session_profile": {"active_killzone": "london", "liquidity": "high"},
    }
    candidate = {
        "symbol": "EURUSD", "signal": "BUY", "strength": 0.7,
        "strategy": "test", "estimated_rr": 1.3,
    }
    ev = evaluate_candidate(state, candidate, _DemoSettings())
    assert ev["council"]["veto"] is True or ev["council"]["meta_score"] < 0.3


def test_scalp_sizing_tight_rr():
    sizing = compute_scalp_sizing("EURUSD", "BUY", _DemoSettings())
    assert sizing["trade_tier"] == "SCALP"
    assert sizing["rr"] >= 1.0
    assert sizing["sl_pips"] <= 8


def test_scalp_risk_approves_strong_candidate():
    state = {"mode": "ACTIVE", "account": {"equity": 10000}}
    candidates = [{
        "symbol": "EURUSD", "signal": "BUY", "strength": 0.72,
        "strategy": "ema_pullback_scalp", "estimated_rr": 1.3,
        "council": {"approved": True, "meta_score": 0.25},
    }]
    with patch("tools.scalp_risk.prop_server_today", return_value="2099-01-01"):
        with patch("tools.scalp_risk.memory.retrieve") as mock_ret:
            def _retrieve(key):
                if key == "scalp_daily_stats":
                    return {"date": "2099-01-01", "trades_opened": 0}
                if key == "open_positions":
                    return []
                return None
            mock_ret.side_effect = _retrieve
            out = approve_candidates(candidates, state, _DemoSettings())
    assert len(out["scalping_approved"]) == 1


@pytest.mark.asyncio
async def test_scalp_pipeline_shadow_mode():
    from tools.scalp_engine import run_scalp_pipeline

    state = {
        "mode": "ACTIVE",
        "session_profile": {"active_killzone": "london", "liquidity": "high"},
        "indicators": {
            "EURUSD": {
                "ema_20": 1.1, "ema_50": 1.09, "close": 1.0998, "rsi_14": 48,
                "adx_14": 25, "trend": "bullish", "macd_hist": 0.001,
                "stoch_k": 45, "atr_14": 0.001,
            },
        },
        "mtf": {}, "ict": {}, "volatility_regimes": {},
        "economic_calendar": {},
        "market_data": {"quotes": [{"symbol": "EURUSD", "bid": 1.1, "ask": 1.10002}]},
    }
    with patch("tools.scalp_engine.get_settings", return_value=_DemoSettings()):
        with patch("tools.scalp_engine.run_cheap_scan") as mock_cheap:
            mock_cheap.return_value = {
                "scanned_symbols_count": 55,
                "top_deep_symbols": ["EURUSD"],
                "cheap_ranked": [],
            }
            with patch("tools.scalp_engine.deep_scan_symbols", new_callable=AsyncMock) as mock_deep:
                mock_deep.return_value = {
                    "scalping_candidates_count": 1,
                    "top_scalping_candidates": [{
                        "symbol": "EURUSD", "signal": "BUY", "strength": 0.72,
                        "strategy": "ema_pullback_scalp", "estimated_rr": 1.3,
                    }],
                }
                with patch("tools.scalp_engine.memory.store"):
                    report = await run_scalp_pipeline(state)
    assert report["scalping_enabled"] is True
    assert report["shadow_logged"] >= 0
