"""Emergency guard + bridge ticket + langchain stubs."""
from __future__ import annotations

import sys
from types import ModuleType
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from tools import emergency_guard, memory


@pytest.mark.asyncio
async def test_soft_breach_locks_after_liquidation():
    settings = MagicMock()
    settings.emergency_soft_cap_pct = 3.5
    settings.max_daily_drawdown_pct = 4.0
    settings.fn_max_daily_loss_pct = 5.0
    settings.trading_state = "ACTIVE"
    settings.active_fail_closed_no_account = True
    settings.mt5_bridge_url = "http://127.0.0.1:5555"
    settings.mt5_bridge_secret = ""
    settings.has_telegram = False

    snap = {
        "available": True,
        "daily_drawdown_pct": 3.6,
        "equity": 9650.0,
        "balance": 9700.0,
    }

    with patch("tools.emergency_guard.get_settings", return_value=settings):
        with patch("tools.emergency_guard.is_daily_locked", return_value=False):
            with patch("tools.emergency_guard.market_hours.market_status", return_value={"is_closed": False}):
                with patch("tools.emergency_guard.account_state.refresh_account", new=AsyncMock(return_value=snap)):
                    with patch("tools.emergency_guard.liquidate_all_positions", new=AsyncMock(return_value={"closed": 1})):
                        with patch("tools.emergency_guard.set_daily_lockout") as lock_fn:
                            lock_fn.return_value = {"date": "2026-06-20", "reason": "soft"}
                            result = await emergency_guard.evaluate({"mode": "ACTIVE"})

    assert result["soft_breach"] is True
    assert result["locked"] is True
    assert result["tripped_now"] is True
    lock_fn.assert_called_once()


def test_langchain_core_tools_stub_import():
    from tests.conftest import _stub_langchain_core_tools
    for name in list(sys.modules):
        if name.startswith("langchain_core"):
            del sys.modules[name]
    _stub_langchain_core_tools()
    from langchain_core.tools import tool  # noqa: F401

    @tool
    def demo_tool(x: str) -> str:
        return x

    assert demo_tool("ok") == "ok"
