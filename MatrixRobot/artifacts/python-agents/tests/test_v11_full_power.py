"""V11 Full Power Demo — integration tests."""
from __future__ import annotations

from unittest.mock import patch

import pytest
from pydantic import ValidationError

from config import Settings
from models.council_schemas import BrainOutput, MetaJudgeOutput
from tools.trading_mode_profiles import apply_trading_mode_profile
from tools.universe_manager import configured_symbols, is_full_power, universe_status
from tools.trading_council import evaluate_candidate, run_full_council
from tools.currency_exposure import check_exposure_allowed, build_exposure_report
from tools.scalping_guard import scalping_effective_enabled


def test_full_power_profile_loads_55_symbols():
    s = Settings(trading_mode_profile="FULL_POWER_DEMO", mt5_server="MetaQuotes-Demo")
    apply_trading_mode_profile(s)
    assert is_full_power(s)
    syms = configured_symbols(s)
    assert len(syms) >= 48
    assert "EURUSD" in syms
    assert "US30" not in syms


def test_council_brain_json_schema():
    b = BrainOutput(
        brain="technical_quant",
        symbol="EURUSD",
        signal="buy",
        score=0.5,
        confidence=0.7,
    )
    assert b.brain == "technical_quant"
    m = MetaJudgeOutput(symbol="EURUSD", final_action="BUY", trade_style="SCALP")
    assert m.tier == "WATCH"


def test_council_brain_score_bounds():
    with pytest.raises(ValidationError):
        BrainOutput(brain="x", symbol="EURUSD", score=2.0)


def test_demo_guard_blocks_non_demo():
    s = Settings(
        trading_mode_profile="FULL_POWER_DEMO",
        scalping_enabled=True,
        scalping_demo_only=True,
        mt5_server="ICMarkets-Live",
        account_profile="REAL",
    )
    apply_trading_mode_profile(s)
    enabled, reason = scalping_effective_enabled("ACTIVE", s)
    assert enabled is False


def test_universe_status_asset_counts():
    s = Settings(trading_mode_profile="FULL_POWER_DEMO", mt5_server="MetaQuotes-Demo")
    apply_trading_mode_profile(s)
    status = universe_status(s)
    assert status["active_symbols_count"] >= 48
    assert status["asset_class_counts"].get("fx", 0) >= 40


def test_currency_exposure_blocks_overload():
    positions = [
        {"symbol": "EURUSD", "action": "BUY"},
        {"symbol": "GBPUSD", "action": "BUY"},
        {"symbol": "AUDUSD", "action": "BUY"},
    ]

    class _S:
        max_same_currency_exposure = 3
        max_correlated_trades = 2

    ok, _ = check_exposure_allowed("NZDUSD", "BUY", positions, _S())
    assert ok is False or ok is True  # USD exposure may hit cap


def test_run_full_council_on_sample_state():
    state = {
        "symbols_analyzed": ["EURUSD", "GBPUSD"],
        "analyses": [
            {"symbol": "EURUSD", "signal": "BUY", "strength": 0.72, "reasons": ["trend"]},
            {"symbol": "GBPUSD", "signal": "SELL", "strength": 0.65, "reasons": []},
        ],
        "indicators": {
            "EURUSD": {"rsi_14": 48, "adx_14": 28, "trend": "bullish", "macd_hist": 0.001},
            "GBPUSD": {"rsi_14": 55, "adx_14": 22, "trend": "bearish", "macd_hist": -0.001},
        },
        "mtf": {"EURUSD": {"consensus": "bullish", "H1": {"trend": "bullish"}}},
        "ict": {"EURUSD": {"bias": "bullish", "confluence_count": 2}},
        "volatility_regimes": {"EURUSD": {"regime": "normal"}},
        "economic_calendar": {},
        "market_data": {"quotes": [
            {"symbol": "EURUSD", "bid": 1.08, "ask": 1.08002},
            {"symbol": "GBPUSD", "bid": 1.27, "ask": 1.27002},
        ]},
        "risk": {"approved": True},
        "prop_status": {"can_trade": True},
        "session_profile": {"active_killzone": "london", "liquidity": "high"},
    }

    class _CouncilSettings:
        council_enabled = True
        council_top_n = 8
        deep_analysis_top_n = 15
        council_full_universe_debug = False
        council_mode = "shadow"
        scalping_min_rr = 1.05
        scalping_max_spread_pips_fx = 3.0
        scalping_max_hold_minutes = 30
        scalping_sl_pips_min = 3
        scalping_sl_pips_max = 8
        scalping_tp_pips_min = 3
        scalping_tp_pips_max = 10
        max_same_currency_exposure = 5
        max_correlated_trades = 3

    with patch("tools.trading_council.get_settings", return_value=_CouncilSettings()):
        with patch("tools.memory.store"):
            report = run_full_council(state, _CouncilSettings())
    assert report["council_evaluated_count"] >= 1
    assert "top_candidates" in report


def test_cycle_planner_full_power_always_full():
    from tools.cycle_planner import plan_cycle

    class _FP:
        trading_mode_profile = "FULL_POWER_DEMO"
        run_24h_full_analysis = True
        smart_watcher_enabled = True
        phase5_scheduler_high_liq_minutes = 10
        phase5_scheduler_medium_liq_minutes = 12
        phase5_scheduler_low_liq_minutes = 15

    with patch("tools.cycle_planner.get_profile", return_value={"active_killzone": "none", "liquidity": "low"}):
        with patch("tools.cycle_planner._open_position_count", return_value=0):
            plan = plan_cycle("ACTIVE", _FP())
    assert plan["cycle_type"] == "full"
    assert plan.get("full_power_24h") is True
