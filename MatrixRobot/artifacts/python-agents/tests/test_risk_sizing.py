"""Unit tests for compute_safe_sizing — financial risk must never exceed budget."""
from __future__ import annotations

import pytest

from agents.risk_agent import compute_safe_sizing, pip_size_for


class _Settings:
    max_risk_per_trade_pct = 0.8
    max_daily_drawdown_pct = 4.0
    max_total_drawdown_pct = 9.0
    max_total_open_risk_pct = 3.0
    sizing_safety_buffer_pct = 0.3


def test_pip_size_eurusd():
    assert pip_size_for("EURUSD") == 0.0001


def test_pip_size_xauusd():
    assert pip_size_for("XAUUSD") == 0.10


def test_pip_size_usdjpy():
    assert pip_size_for("USDJPY") == 0.01


def test_approved_trade_within_budget():
    s = _Settings()
    result = compute_safe_sizing(
        symbol="EURUSD",
        strength=0.75,
        atr=0.0012,
        equity=10_000.0,
        starting_balance=10_000.0,
        current_open_risk_pct=0.0,
        prop_status={"daily_loss_pct": 0.0, "total_loss_pct": 0.0},
        settings=s,
    )
    assert result["rejected"] is False
    assert result["lots"] >= 0.01
    assert result["sl_pips"] >= 15
    assert result["risk_usd"] <= result["budget_usd"] + 0.01


def test_rejected_when_no_daily_dd_room():
    s = _Settings()
    result = compute_safe_sizing(
        symbol="EURUSD",
        strength=1.0,
        atr=0.001,
        equity=10_000.0,
        starting_balance=10_000.0,
        current_open_risk_pct=0.0,
        prop_status={"daily_loss_pct": 4.0, "total_loss_pct": 0.0},
        settings=s,
    )
    assert result["rejected"] is True
    assert result["lots"] == 0.0


def test_rejected_when_min_lot_exceeds_budget():
    s = _Settings()
    result = compute_safe_sizing(
        symbol="EURUSD",
        strength=0.1,
        atr=0.05,
        equity=100.0,
        starting_balance=100.0,
        current_open_risk_pct=2.9,
        prop_status={"daily_loss_pct": 0.0, "total_loss_pct": 0.0},
        settings=s,
    )
    assert result["rejected"] is True
    assert "Minimum lot" in (result.get("reject_reason") or "")


def test_xauusd_lots_respect_budget_with_correct_pip_value():
    """Gold must not be sized 10× too large (PIP_VALUE must match MT5 $10/pip/lot)."""
    s = _Settings()
    result = compute_safe_sizing(
        symbol="XAUUSD",
        strength=0.75,
        atr=10.0,
        equity=10_000.0,
        starting_balance=10_000.0,
        current_open_risk_pct=0.0,
        prop_status={"daily_loss_pct": 0.0, "total_loss_pct": 0.0},
        settings=s,
    )
    assert result["rejected"] is False
    assert result["lots"] <= 0.10
    assert result["risk_usd"] <= result["budget_usd"] + 0.01


def test_vol_mult_never_increases_risk_above_cap():
    s = _Settings()
    base = compute_safe_sizing(
        symbol="EURUSD",
        strength=0.8,
        atr=0.001,
        equity=10_000.0,
        starting_balance=10_000.0,
        current_open_risk_pct=0.0,
        prop_status={"daily_loss_pct": 0.0, "total_loss_pct": 0.0},
        settings=s,
        vol_mult=1.0,
    )
    boosted = compute_safe_sizing(
        symbol="EURUSD",
        strength=0.8,
        atr=0.001,
        equity=10_000.0,
        starting_balance=10_000.0,
        current_open_risk_pct=0.0,
        prop_status={"daily_loss_pct": 0.0, "total_loss_pct": 0.0},
        settings=s,
        vol_mult=1.5,
    )
    assert base["rejected"] is False
    assert boosted["rejected"] is False
    assert boosted["lots"] <= base["lots"]
