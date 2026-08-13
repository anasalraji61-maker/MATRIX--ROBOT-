"""Tests for Evolution Entity (cloud continuous self-development)."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from tools import evolution_entity as ee


@pytest.fixture()
def isolated(tmp_path, monkeypatch):
    monkeypatch.setattr(ee, "_STATE_DIR", tmp_path)
    monkeypatch.setattr(ee, "_FILE", tmp_path / "evolution_entity.json")
    ee._last_tick = None
    ee._last_result = None
    ee._running_tick = False
    yield tmp_path


def _s(**kw):
    m = MagicMock()
    m.evolution_entity_enabled = True
    m.evolution_entity_interval_minutes = 15
    m.evolution_digest_hours = 6.0
    m.has_telegram = False
    for k, v in kw.items():
        setattr(m, k, v)
    return m


@pytest.mark.asyncio
async def test_tick_investigates_losses(isolated):
    loss = {
        "trade_id": "T1",
        "symbol": "EURUSD",
        "side": "BUY",
        "pnl": -12.0,
        "close_reason": "stop_loss",
    }
    with patch.object(ee, "_settings", return_value=_s()), \
         patch.object(ee, "_harvest_unseen_losses", AsyncMock(return_value=[loss])), \
         patch.object(ee, "_investigate_batch", AsyncMock(return_value=[{
             "enabled": True,
             "case": {"symbol": "EURUSD"},
         }])), \
         patch.object(ee, "_consolidate", return_value={"escalated": [], "penalty_keys": 0}), \
         patch.object(ee, "_maybe_digest", AsyncMock()):
        r = await ee.run_tick(force=True)
    assert r["ok"] is True
    assert r["investigated"] == 1
    snap = ee.get_snapshot(_s())
    assert snap["runs_on"] == "vps_cloud_brain"
    assert snap["ticks"] >= 1
    assert snap["generation"] >= 1


@pytest.mark.asyncio
async def test_disabled(isolated):
    with patch.object(ee, "_settings", return_value=_s(evolution_entity_enabled=False)):
        r = await ee.run_tick(force=False)
    assert r.get("reason") == "evolution_entity_disabled"


def test_snapshot_mission(isolated):
    snap = ee.get_snapshot(_s())
    assert "كيان مستقل" in snap["mission_ar"]
    assert snap["laptop_role"] == "heavy_pytorch_training_only"
