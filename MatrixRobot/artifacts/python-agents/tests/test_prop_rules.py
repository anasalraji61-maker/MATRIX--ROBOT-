"""Unit tests for prop_rules helpers (no MT5 bridge required)."""
from __future__ import annotations

from tools import prop_rules


def test_open_risk_pct_empty_positions():
    assert prop_rules.open_risk_pct([], 10_000.0) == 0.0


def test_open_risk_pct_with_stop():
    positions = [{
        "symbol": "EURUSD",
        "entry_price": 1.1000,
        "stop_loss": 1.0985,
        "lots": 0.10,
    }]
    pct = prop_rules.open_risk_pct(positions, 10_000.0)
    assert pct > 0.0
    assert pct < 5.0


def test_margin_used_pct_zero_equity():
    assert prop_rules.margin_used_pct([{"symbol": "EURUSD", "lots": 0.1}], 0.0) == 0.0


def test_margin_used_pct_positive():
    positions = [{"symbol": "EURUSD", "lots": 0.1, "entry_price": 1.1}]
    pct = prop_rules.margin_used_pct(positions, 10_000.0)
    assert pct >= 0.0
