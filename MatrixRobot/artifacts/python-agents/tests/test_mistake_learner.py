"""Tests for lightweight mistake learner (auto APE from closed losses)."""
from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from tools import mistake_learner as ml


@pytest.fixture()
def isolated_state(tmp_path, monkeypatch):
    monkeypatch.setattr(ml, "_STATE_DIR", tmp_path)
    monkeypatch.setattr(ml, "_FILE", tmp_path / "mistake_learner.json")
    ape_dir = tmp_path / "ape"
    ape_dir.mkdir()
    from tools import adaptive_policy as ape

    monkeypatch.setattr(ape, "_STATE_DIR", ape_dir)
    monkeypatch.setattr(ape, "_APE_FILE", ape_dir / "adaptive_policy.json")
    yield tmp_path


def _settings(**kwargs):
    s = MagicMock()
    s.mistake_learner_enabled = True
    s.mistake_learner_pause_after_symbol_losses = 2
    s.mistake_learner_reduce_risk_after = 3
    s.mistake_learner_tighten_after = 4
    s.mistake_learner_skip_after = 5
    for k, v in kwargs.items():
        setattr(s, k, v)
    return s


def test_win_resets_consecutive_losses(isolated_state):
    r1 = ml.on_trade_closed(symbol="EURUSD", side="BUY", pnl=-10.0, settings=_settings())
    assert r1["consecutive_losses"] == 1
    r2 = ml.on_trade_closed(symbol="EURUSD", side="BUY", pnl=12.0, settings=_settings())
    assert r2["consecutive_losses"] == 0
    assert r2["lesson_type"] == "win"


def test_two_symbol_losses_pause(isolated_state):
    s = _settings()
    ml.on_trade_closed(symbol="GBPUSD", side="SELL", pnl=-5.0, settings=s)
    r = ml.on_trade_closed(symbol="GBPUSD", side="SELL", pnl=-8.0, settings=s)
    types = [a["type"] for a in r["actions"]]
    assert "PAUSE_SYMBOL" in types
    assert any((a.get("result") or {}).get("success") for a in r["actions"] if a["type"] == "PAUSE_SYMBOL")


def test_three_losses_reduce_risk(isolated_state):
    s = _settings()
    # Different symbols so pause rate-limit does not block REDUCE path entirely
    ml.on_trade_closed(symbol="EURUSD", side="BUY", pnl=-1.0, settings=s)
    ml.on_trade_closed(symbol="GBPUSD", side="BUY", pnl=-1.0, settings=s)
    r = ml.on_trade_closed(symbol="USDJPY", side="BUY", pnl=-1.0, settings=s)
    types = [a["type"] for a in r["actions"]]
    assert "REDUCE_RISK" in types


def test_disabled_skips(isolated_state):
    r = ml.on_trade_closed(
        symbol="EURUSD", side="BUY", pnl=-20.0, settings=_settings(mistake_learner_enabled=False)
    )
    assert r.get("skipped") is True


def test_snapshot_shape(isolated_state):
    ml.on_trade_closed(symbol="EURUSD", side="BUY", pnl=-3.0, settings=_settings())
    snap = ml.get_snapshot(_settings())
    assert snap["enabled"] is True
    assert snap["closes_seen"] >= 1
    assert "thresholds" in snap
    assert len(snap["recent_lessons"]) >= 1
