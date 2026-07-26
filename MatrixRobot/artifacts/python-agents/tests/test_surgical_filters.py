"""Surgical filter gates — quarantine, time window, CHF, XAGUSD."""
from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import patch

import pytest

from tools import surgical_filters as sf


class _Settings:
    symbol_quarantine = "GBPCHF,CADCHF"
    scalping_min_strength = 0.61
    scalping_min_rr = 1.10
    normal_trade_min_strength = 0.68
    normal_trade_require_rr_min = 1.2
    chf_pairs_min_strength = 0.0
    chf_pairs_min_rr = 0.0
    time_filter_09_12_min_strength_bonus = 0.07
    time_filter_09_12_min_rr_bonus = 0.10
    xagusd_risk_multiplier = 0.5
    xagusd_require_breakeven = False
    xagusd_max_single_loss_usd = 30.0


def test_symbol_quarantine_blocks():
  blocked, reason = sf.is_symbol_quarantined("GBPCHF", _Settings())
  assert blocked
  assert "quarantine" in reason.lower()
  ok, _ = sf.is_symbol_quarantined("AUDUSD", _Settings())
  assert not ok


def test_scalp_gate_passes_good_signal():
  ok, reason = sf.check_entry_gates(
      "EURUSD", 0.65, 1.15, settings=_Settings(), trade_tier="SCALP",
  )
  assert ok, reason


def test_scalp_gate_blocks_quarantine():
  ok, reason = sf.check_entry_gates(
      "CADCHF", 0.90, 1.50, settings=_Settings(), trade_tier="SCALP",
  )
  assert not ok
  assert "quarantine" in reason.lower()


@patch("tools.surgical_filters.prop_server_now")
def test_time_window_raises_threshold(mock_now):
  mock_now.return_value = datetime(2026, 6, 24, 10, 0, tzinfo=timezone.utc)
  ok, reason = sf.check_entry_gates(
      "EURUSD", 0.64, 1.15, settings=_Settings(), trade_tier="SCALP",
  )
  assert not ok
  assert "strength" in reason.lower()


def test_audchf_exempt_from_chf_pair():
  assert not sf.is_chf_pair("AUDCHF")
  s = _Settings()
  s.chf_pairs_min_strength = 0.68
  ok, _ = sf.check_entry_gates("AUDCHF", 0.62, 1.1, settings=s, trade_tier="SCALP")
  assert ok


def test_xagusd_risk_multiplier():
  assert sf.xagusd_risk_multiplier("XAGUSD", _Settings()) == 0.5
  assert sf.xagusd_risk_multiplier("EURUSD", _Settings()) == 1.0
