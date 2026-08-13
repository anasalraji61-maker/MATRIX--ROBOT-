"""Tests for Smart Watcher cycle planner."""
from __future__ import annotations

from unittest.mock import patch

from tools.cycle_planner import plan_cycle, next_killzone_start


class _Settings:
    smart_watcher_enabled = True
    phase5_intraday_enabled = True
    phase5_scheduler_high_liq_minutes = 20
    phase5_scheduler_medium_liq_minutes = 60
    phase5_scheduler_low_liq_minutes = 90
    off_session_scanner_minutes = 25
    off_session_maintenance_minutes = 12
    session_filter_mode = "tiered"
    phase5_session_require_killzone = True
    phase5_block_low_liquidity = True
    phase5_scheduler_adaptive = True
    phase5_sl_atr_mult_high = 1.0
    phase5_sl_atr_mult_medium = 1.25
    phase5_sl_atr_mult_low = 1.5
    phase5_tp_rr_high = 1.5
    phase5_tp_rr_medium = 1.75
    phase5_tp_rr_low = 2.0
    scheduler_interval_minutes = 90
    tiered_block_metals_outside_kz = True
    tiered_block_indices_outside_kz = True
    estimated_full_cycle_cost_usd = 0.18
    estimated_scanner_cycle_cost_usd = 0.02
    estimated_maintenance_cycle_cost_usd = 0.005
    estimated_brain_escalation_cost_usd = 0.06


def test_plan_full_during_london():
    with patch("tools.session_engine._active_killzone", return_value="london"), \
         patch("tools.cycle_planner._open_position_count", return_value=0):
        p = plan_cycle("ACTIVE", _Settings())
    assert p["cycle_type"] == "full"
    assert p["brain_active"] is True
    assert p["scheduler_interval_minutes"] == 20


def test_plan_scanner_outside_killzone_no_positions():
    with patch("tools.session_engine._active_killzone", return_value="none"), \
         patch("tools.cycle_planner._open_position_count", return_value=0):
        p = plan_cycle("ACTIVE", _Settings())
    assert p["cycle_type"] == "scanner"
    assert p["brain_active"] is False
    assert p["scheduler_interval_minutes"] == 25


def test_plan_maintenance_outside_with_open_positions():
    with patch("tools.session_engine._active_killzone", return_value="none"), \
         patch("tools.cycle_planner._open_position_count", return_value=2):
        p = plan_cycle("ACTIVE", _Settings())
    assert p["cycle_type"] == "maintenance"
    assert p["scheduler_interval_minutes"] == 12


def test_plan_asian_full_brain():
    with patch("tools.session_engine._active_killzone", return_value="asian"), \
         patch("tools.cycle_planner._open_position_count", return_value=0):
        p = plan_cycle("ACTIVE", _Settings())
    assert p["cycle_type"] == "full"
    assert p["brain_active"] is True
    assert p["scheduler_interval_minutes"] == 60


def test_next_killzone_before_london():
    from datetime import datetime, timezone
    now = datetime(2026, 6, 22, 5, 30, tzinfo=timezone.utc)
    nxt, name = next_killzone_start(now)
    assert name == "london"
    assert nxt.hour == 7
