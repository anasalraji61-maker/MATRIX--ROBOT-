"""V8 ChatGPT follow-up — batch halt, manual-check persistence, bridge close, lot steps."""
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from models.schemas import ExecutionResult
from tools import bridge_manual
from tools.bridge_manual import MANUAL_CHECK_CLEAR_PHRASE
from tools.risk_sizing import compute_safe_sizing, quantize_lot


class _Settings:
    max_risk_per_trade_pct = 0.8
    max_daily_drawdown_pct = 4.0
    max_total_drawdown_pct = 9.0
    max_total_open_risk_pct = 3.0
    sizing_safety_buffer_pct = 0.3
    account_profile = "FN_CHALLENGE"
    mt5_bridge_url = "http://127.0.0.1:5555"
    economic_calendar_enabled = False
    correlation_guard_enabled = False
    require_stop_loss = True
    max_concurrent_positions = 5
    max_trades_per_day = 30
    enable_small_trades = True
    small_trade_min_strength = 0.60
    normal_trade_min_strength = 0.68
    small_trade_max_open = 4
    small_trade_max_per_day = 12
    volatility_regime_enabled = False
    normal_trade_require_rr_min = 1.5
    small_trade_require_rr_min = 1.2


@pytest.mark.asyncio
async def test_manual_check_block_has_no_ttl():
    bridge_manual.clear()
    with patch("tools.bridge_manual.get_settings") as gs:
        gs.return_value = MagicMock(has_telegram=False)
        with patch("tools.bridge_manual.memory.store") as store:
            await bridge_manual.record_manual_check_required("EURUSD", {"order_id": 1})
            for call in store.call_args_list:
                assert call.kwargs.get("ttl_seconds") == 0
    bridge_manual.clear()


@pytest.mark.asyncio
async def test_batch_halts_after_manual_check_on_second_trade():
    from agents import execution_agent as ex

    bridge_manual.clear()
    manual = ExecutionResult(
        executed=False,
        mode="ACTIVE",
        symbol="EURUSD",
        action="BUY",
        manual_check_required=True,
        message="CRITICAL: manual check",
    )
    would_execute = ExecutionResult(
        executed=True,
        mode="ACTIVE",
        symbol="GBPUSD",
        action="BUY",
        trade_id="2",
        lots=0.01,
        entry_price=1.27,
        stop_loss=1.26,
        take_profit=1.28,
        message="filled",
    )

    state = {
        "mode": "ACTIVE",
        "account": {"equity": 10000, "starting_balance": 10000},
        "prop_status": {"can_trade": True, "daily_loss_pct": 0, "total_loss_pct": 0},
        "market_data": {
            "quotes": [
                {"symbol": "EURUSD", "bid": 1.08, "ask": 1.0802},
                {"symbol": "GBPUSD", "bid": 1.27, "ask": 1.2702},
            ],
        },
        "indicators": {
            "EURUSD": {"atr_14": 0.001},
            "GBPUSD": {"atr_14": 0.001},
        },
        "decision": {
            "approved_trades": [
                {"symbol": "EURUSD", "signal": "BUY", "strength": 0.9},
                {"symbol": "GBPUSD", "signal": "BUY", "strength": 0.85},
            ],
        },
        "approved_risk_trades": [
            {
                "symbol": "EURUSD", "signal": "BUY",
                "sizing": {
                    "lots": 0.01, "sl_pips": 20, "tp_pips": 40, "rr": 2.0,
                    "pip": 0.0001, "pip_val": 10.0, "rejected": False,
                },
            },
            {
                "symbol": "GBPUSD", "signal": "BUY",
                "sizing": {
                    "lots": 0.01, "sl_pips": 20, "tp_pips": 40, "rr": 2.0,
                    "pip": 0.0001, "pip_val": 10.0, "rejected": False,
                },
            },
        ],
        "session_profile": {"enabled": False},
    }

    calls = {"n": 0}

    async def fake_execute(*args, **kwargs):
        calls["n"] += 1
        if calls["n"] == 1:
            with patch("tools.bridge_manual.is_blocking", return_value=True):
                return manual
        return would_execute

    with patch.object(ex, "_execute_one", side_effect=fake_execute):
        with patch.object(ex.position_reconciler, "ensure_synced", new=AsyncMock(return_value=True)):
            with patch.object(ex.account_state, "sync_open_positions", new=AsyncMock(return_value=[])):
                with patch.object(ex.account_state, "trades_today_count", return_value=0):
                    with patch.object(ex.prop_rules, "evaluate", new=AsyncMock(return_value=MagicMock(can_trade=True))):
                        with patch("tools.liquidity_guard.check_spread", return_value=(True, "")):
                            with patch("tools.bridge_manual.record_manual_check_required", new=AsyncMock()):
                                primary, executions = await ex._run_primary(
                                    state, _Settings(), "ACTIVE",
                                    state["decision"]["approved_trades"],
                                )

    symbols_attempted = [e.get("symbol") for e in executions if e.get("symbol")]
    assert symbols_attempted == ["EURUSD"]
    assert any("Batch halted" in (e.get("message") or "") for e in executions)
    assert calls["n"] == 1
    bridge_manual.clear()


@pytest.mark.asyncio
async def test_clear_manual_check_requires_phrase():
    from fastapi import HTTPException
    from routes.circuit import clear_manual_check, ClearManualCheckRequest

    bridge_manual.clear()
    with patch("tools.bridge_manual.is_blocking", return_value=True):
        with patch("tools.bridge_manual.get_status", return_value={"symbol": "EURUSD"}):
            with pytest.raises(HTTPException):
                await clear_manual_check(ClearManualCheckRequest(confirm="wrong phrase"))

    bridge_manual.clear()
    with patch("routes.circuit.is_blocking", return_value=True):
        with patch("routes.circuit.get_status", return_value={"symbol": "EURUSD"}):
            with patch("routes.circuit.clear") as cleared:
                out = await clear_manual_check(
                    ClearManualCheckRequest(confirm=MANUAL_CHECK_CLEAR_PHRASE),
                )
    assert out["cleared"] is True
    cleared.assert_called_once()


def test_close_trade_order_send_none():
    from tools.bridge_close import close_position

    pos = SimpleNamespace(type=0, symbol="EURUSD", volume=0.01, magic=123)
    tick = SimpleNamespace(bid=1.08, ask=1.0802)
    mt5 = SimpleNamespace(
        positions_get=lambda ticket: [pos],
        symbol_info_tick=lambda sym: tick,
        order_send=lambda req: None,
        ORDER_TYPE_BUY=0,
        ORDER_TYPE_SELL=1,
        ORDER_FILLING_FOK=0,
        ORDER_FILLING_IOC=1,
        ORDER_FILLING_RETURN=2,
        TRADE_ACTION_DEAL=1,
        ORDER_TIME_GTC=0,
        TRADE_RETCODE_DONE=10009,
    )
    out = close_position(mt5, ticket=999, comment="test")
    assert out["success"] is False
    assert out["retcode"] == -1
    assert "None" in out["comment"]


def test_close_trade_already_closed():
    from tools.bridge_close import close_position

    mt5 = SimpleNamespace(positions_get=lambda ticket: [])
    out = close_position(mt5, ticket=999, comment="test")
    assert out["success"] is True
    assert out["already_closed"] is True


def test_close_trade_tick_unavailable():
    from tools.bridge_close import close_position

    pos = SimpleNamespace(type=0, symbol="EURUSD", volume=0.01, magic=123)
    mt5 = SimpleNamespace(
        positions_get=lambda ticket: [pos],
        symbol_info_tick=lambda sym: None,
    )
    out = close_position(mt5, ticket=999, comment="test")
    assert out["success"] is False
    assert "tick" in out["comment"].lower()


@pytest.mark.parametrize("raw,min_lot,step,expected", [
    (0.05, 0.01, 0.01, 0.05),
    (0.055, 0.01, 0.01, 0.05),
    (0.005, 0.01, 0.01, 0.0),
    (0.25, 0.1, 0.1, 0.2),
    (2.5, 1.0, 1.0, 2.0),
])
def test_quantize_lot(raw, min_lot, step, expected):
    assert quantize_lot(raw, min_lot, step) == expected


def test_sizing_uses_broker_min_lot_us500():
    s = _Settings()
    result = compute_safe_sizing(
        symbol="US500",
        strength=0.75,
        atr=10.0,
        equity=10_000.0,
        starting_balance=10_000.0,
        current_open_risk_pct=0.0,
        prop_status={"daily_loss_pct": 0.0, "total_loss_pct": 0.0},
        settings=s,
    )
    assert result["min_lot"] == 0.1
    assert result["lot_step"] == 0.1
    if not result["rejected"]:
        assert result["lots"] >= 0.1
        assert abs(result["lots"] * 10 - round(result["lots"] * 10)) < 1e-6


def test_sizing_us30_min_lot_one():
    s = _Settings()
    result = compute_safe_sizing(
        symbol="US30",
        strength=0.75,
        atr=50.0,
        equity=50_000.0,
        starting_balance=50_000.0,
        current_open_risk_pct=0.0,
        prop_status={"daily_loss_pct": 0.0, "total_loss_pct": 0.0},
        settings=s,
    )
    assert result["min_lot"] == 1.0
    if not result["rejected"]:
        assert result["lots"] >= 1.0
        assert result["lots"] == int(result["lots"])
