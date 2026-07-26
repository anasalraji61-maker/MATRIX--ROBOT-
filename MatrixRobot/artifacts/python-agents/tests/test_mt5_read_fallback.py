"""ACTIVE read-path must not fall back to native MT5 when bridge is configured."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from tools import mt5_bridge


class _Settings:
    mt5_bridge_url = "http://127.0.0.1:5555"
    active_allow_native_mt5 = False
    trading_state = "ACTIVE"
    has_mt5 = True


@pytest.mark.asyncio
async def test_get_live_account_no_native_fallback_in_active():
    with patch.object(mt5_bridge, "get_settings", return_value=_Settings()):
        with patch.object(mt5_bridge, "_http_account", new=AsyncMock(side_effect=ConnectionError("down"))):
            with patch.object(mt5_bridge, "_init_mt5") as native_init:
                result = await mt5_bridge.get_live_account()
    assert result is None
    native_init.assert_not_called()


@pytest.mark.asyncio
async def test_get_live_positions_no_native_fallback_in_active():
    with patch.object(mt5_bridge, "get_settings", return_value=_Settings()):
        with patch.object(mt5_bridge, "_http_positions", new=AsyncMock(side_effect=ConnectionError("down"))):
            with patch.object(mt5_bridge, "_init_mt5") as native_init:
                result = await mt5_bridge.get_live_positions()
    assert result == []
    native_init.assert_not_called()
