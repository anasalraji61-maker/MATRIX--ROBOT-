"""Tests for loss investigator — post-mortem + thinking change."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from tools import loss_investigator as li


@pytest.fixture()
def isolated(tmp_path, monkeypatch):
    monkeypatch.setattr(li, "_STATE_DIR", tmp_path)
    monkeypatch.setattr(li, "_FILE", tmp_path / "loss_investigations.json")
    monkeypatch.setattr(li, "_BIASES_FILE", tmp_path / "thinking_biases.json")
    yield tmp_path


def _s(**kw):
    m = MagicMock()
    m.loss_investigator_enabled = True
    m.loss_investigator_use_llm = False
    m.has_llm = False
    for k, v in kw.items():
        setattr(m, k, v)
    return m


def test_investigate_changes_thinking(isolated):
    with patch.object(li, "_find_brain_decision", return_value={
        "symbol": "EURUSD", "signal": "BUY", "strength": 0.62,
        "reasons": ["mixed signals", "conflict MTF"],
        "llm_analysis": "maybe a possible long",
    }):
        r = li.investigate_loss(
            symbol="EURUSD", side="BUY", pnl=-18.0, reason="stop_loss",
            trade_id="1", settings=_s(),
        )
    assert r.get("case")
    assert "thinking_errors" in r["case"]["diagnosis"]
    assert li.strength_penalty("EURUSD", "BUY") > 0
    notes = li.brain_context_notes("EURUSD")
    assert "LESSONS" in notes
    snap = li.get_snapshot(_s())
    assert snap["stats"]["investigated"] >= 1
    assert snap["pending_advice"]


def test_skip_wins(isolated):
    r = li.investigate_loss(symbol="EURUSD", side="BUY", pnl=10.0, settings=_s())
    assert r.get("skipped") is True


def test_disabled(isolated):
    r = li.investigate_loss(
        symbol="EURUSD", side="BUY", pnl=-5.0,
        settings=_s(loss_investigator_enabled=False),
    )
    assert r.get("skipped") is True
