"""Manual-check alert + broker spec helpers."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from tools import bridge_manual, symbol_specs


@pytest.mark.asyncio
async def test_manual_check_records_and_blocks():
    bridge_manual.clear()
    with patch("tools.bridge_manual.get_settings") as gs:
        gs.return_value = MagicMock(has_telegram=True)
        with patch("tools.telegram_alerts.alert_manual_check_required", new=AsyncMock()) as alert:
            rec = await bridge_manual.record_manual_check_required(
                "EURUSD", {"order_id": 12345, "comment": "ticket unresolved"},
            )
    assert rec["symbol"] == "EURUSD"
    assert bridge_manual.is_blocking() is True
    assert bridge_manual.get_status()["order_id"] == 12345
    alert.assert_awaited_once()
    bridge_manual.clear()


def test_spec_from_broker_info_index():
    spec = symbol_specs.spec_from_broker_info({
        "symbol": "US500",
        "point": 0.01,
        "digits": 2,
        "trade_tick_value": 0.5,
        "trade_tick_size": 0.01,
        "volume_min": 0.1,
        "volume_step": 0.1,
    })
    assert spec is not None
    assert spec.pip_size == 0.01
    assert spec.source == "mt5"
    assert spec.volume_min == 0.1


@pytest.mark.asyncio
async def test_open_trade_manual_check_triggers_alert():
    from tools.mt5_bridge import open_trade

    settings = MagicMock()
    settings.mt5_bridge_url = "http://127.0.0.1:5555"
    settings.active_allow_native_mt5 = False
    settings.has_mt5 = False
    settings.active_verify_sltp_after_open = True
    settings.has_telegram = False

    bridge_manual.clear()
    with patch("tools.mt5_bridge.get_settings", return_value=settings):
        with patch("tools.mt5_bridge._http_open", new=AsyncMock(return_value={
            "success": False,
            "manual_check_required": True,
            "order_id": 999,
            "comment": "ticket unresolved",
        })):
            with patch("tools.bridge_manual.record_manual_check_required", new=AsyncMock()) as rec:
                result = await open_trade("EURUSD", "BUY", 0.01, 1.08, 1.09, "ACTIVE")
    assert result.executed is False
    assert result.manual_check_required is True
    assert "CRITICAL" in result.message
    rec.assert_awaited_once()
    bridge_manual.clear()
