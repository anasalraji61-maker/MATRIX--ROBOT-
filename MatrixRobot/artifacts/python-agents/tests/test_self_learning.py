"""Tests for unified self-learning across robot layers."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from tools import self_learning as sl


@pytest.fixture()
def isolated(tmp_path, monkeypatch):
    monkeypatch.setattr(sl, "_STATE_DIR", tmp_path)
    monkeypatch.setattr(sl, "_FILE", tmp_path / "self_learning.json")
    from tools import adaptive_policy as ape
    ape_dir = tmp_path / "ape"
    ape_dir.mkdir()
    monkeypatch.setattr(ape, "_STATE_DIR", ape_dir)
    monkeypatch.setattr(ape, "_APE_FILE", ape_dir / "adaptive_policy.json")
    from tools import mistake_learner as ml
    monkeypatch.setattr(ml, "_STATE_DIR", tmp_path)
    monkeypatch.setattr(ml, "_FILE", tmp_path / "mistake_learner.json")
    yield tmp_path


def _s(**kw):
    m = MagicMock()
    m.self_learning_enabled = True
    m.self_learning_repeat_threshold = 2
    m.self_learning_block_hours = 12.0
    m.mistake_learner_enabled = True
    m.mistake_learner_pause_after_symbol_losses = 2
    m.mistake_learner_reduce_risk_after = 3
    m.mistake_learner_tighten_after = 4
    m.mistake_learner_skip_after = 5
    for k, v in kw.items():
        setattr(m, k, v)
    return m


def test_repeat_creates_block(isolated):
    sl.record_event(layer="execution", kind="execution_fail", symbol="EURUSD", side="BUY",
                    reason="bridge timeout", settings=_s())
    r = sl.record_event(layer="execution", kind="execution_fail", symbol="EURUSD", side="BUY",
                        reason="bridge timeout", settings=_s())
    assert r.get("block") is not None
    blocked, why = sl.is_blocked("EURUSD", "BUY")
    assert blocked is True
    assert "Prevent" in why or "repeat" in why.lower() or "bridge" in why.lower()


def test_filter_analyses_removes_blocked(isolated):
    sl.record_event(layer="trade", kind="trade_loss", symbol="GBPUSD", side="SELL",
                    reason="sl hit", severity="high", settings=_s())
    sl.record_event(layer="trade", kind="trade_loss", symbol="GBPUSD", side="SELL",
                    reason="sl hit", severity="high", settings=_s())
    kept, removed = sl.filter_analyses([
        {"symbol": "GBPUSD", "signal": "SELL", "strength": 0.8},
        {"symbol": "EURUSD", "signal": "BUY", "strength": 0.7},
    ], _s())
    assert len(removed) == 1
    assert removed[0]["symbol"] == "GBPUSD"
    assert any(a["symbol"] == "EURUSD" for a in kept)


def test_ingest_cycle_records_errors(isolated):
    report = sl.ingest_cycle({
        "errors": ["OpenAI request failed 401"],
        "risk": {"rejections": {"USDJPY": ["spread too wide"]}},
        "executions": [{"executed": False, "symbol": "AUDUSD", "action": "BUY", "message": "MT5 bridge down"}],
        "decision": {"action": "HOLD", "risk_note": "ok"},
    }, cycle_id="abc", settings=_s())
    assert report["recorded"] >= 2
    snap = sl.get_snapshot(_s())
    assert snap["stats"]["events_total"] >= 2


def test_on_trade_closed_delegates(isolated):
    out = sl.on_trade_closed(symbol="EURUSD", side="BUY", pnl=-15.0, reason="stop_loss", settings=_s())
    assert out["self_learning"] is not None
    assert out["mistake_learner"] is not None


def test_disabled(isolated):
    r = sl.record_event(layer="risk", kind="risk_reject", symbol="XAUUSD",
                        reason="cap", settings=_s(self_learning_enabled=False))
    assert r.get("skipped") is True
