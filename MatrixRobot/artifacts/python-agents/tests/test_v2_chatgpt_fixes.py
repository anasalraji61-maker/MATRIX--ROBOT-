"""ChatGPT V2 review — P0 fixes verification."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from tools.twelve_data import _from_td_symbol, fetch_quotes, get_data_meta, reset_data_meta
from tools.data_quality import validate_active_data, active_data_status
from tools import memory


class _Settings:
    has_twelve_data = True
    twelve_data_api_key = "test-key"
    has_polygon = False
    active_require_live_news = True
    active_fail_closed_data = True
    active_fail_closed_no_account = False
    trading_state = "ACTIVE"


def test_index_reverse_mapping():
    assert _from_td_symbol("DJI") == "US30"
    assert _from_td_symbol("SPX") == "US500"
    assert _from_td_symbol("NDX") == "USTEC"
    assert _from_td_symbol("EUR/USD") == "EURUSD"


@pytest.mark.asyncio
async def test_fetch_quotes_us30_not_mock_when_dji_returned():
    reset_data_meta()
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "DJI": {
            "symbol": "DJI",
            "close": "42500.0",
            "bid": "42499.0",
            "ask": "42501.0",
            "percent_change": "0.1",
        }
    }

    class _Client:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            pass

        async def get(self, url, params=None):
            return mock_response

    with patch("tools.twelve_data.get_settings", return_value=_Settings()):
        with patch("tools.twelve_data.httpx.AsyncClient", return_value=_Client()):
            quotes = await fetch_quotes(["US30"])

    assert len(quotes) == 1
    assert quotes[0].symbol == "US30"
    meta = get_data_meta()
    assert "US30" not in meta.get("quotes_mock_symbols", [])


@pytest.mark.asyncio
async def test_supervisor_llm_failure_uses_rule_fallback():
    from agents.supervisor_agent import _llm_decide
    from models.schemas import SupervisorDecision

    memory.store("supervisor_llm_error", None, ttl_seconds=1)

    state = {
        "best_analysis": {"symbol": "EURUSD", "signal": "BUY", "strength": 0.75},
        "risk": {"approved": True},
        "sentiment": {"label": "NEUTRAL", "score": 0.0},
        "analyses": [{"symbol": "EURUSD", "signal": "BUY", "strength": 0.75}],
        "approved_risk_trades": [],
    }
    settings = MagicMock()
    settings.effective_openrouter_key = "sk-or-test"
    settings.effective_openai_key = ""
    settings.max_concurrent_positions = 5
    settings.small_trade_min_strength = 0.6
    settings.normal_trade_min_strength = 0.68
    settings.ml_filter_enabled = False

    with patch("agents.supervisor_agent.build_approved_trades", return_value=[]):
        mock_llm = MagicMock()
        mock_llm.ainvoke = AsyncMock(side_effect=RuntimeError("LLM down"))
        mock_llm_cls = MagicMock(return_value=mock_llm)
        with patch("langchain_openai.ChatOpenAI", mock_llm_cls, create=True):
            decision = await _llm_decide(state, settings, "PAPER_MODE", "ok", 1, 0)

    assert isinstance(decision, SupervisorDecision)
    assert memory.retrieve("supervisor_llm_error") is not None


@pytest.mark.asyncio
async def test_emergency_fail_closed_skip_message():
    from agents.graph import _node_skip

    state = {
        "mode": "ACTIVE",
        "emergency": {
            "locked": True,
            "fail_closed": True,
            "lockout": {"reason": "bridge down"},
        },
        "decision": {},
    }
    out = await _node_skip(state)
    msg = out["execution"]["message"]
    assert "fail-closed" in msg.lower()
    assert "Emergency guard failed" in msg


@pytest.mark.asyncio
async def test_emergency_guard_exception_fail_closed_in_active():
    from agents.graph import _node_emergency

    state = {"mode": "ACTIVE", "errors": []}
    with patch("agents.graph.emergency_guard.evaluate", new=AsyncMock(side_effect=RuntimeError("bridge down"))):
        out = await _node_emergency(state)

    assert out["emergency"]["locked"] is True
    assert out["emergency"].get("fail_closed") is True
    assert out["execution"]["executed"] is False
    assert "fail-closed" in out["execution"]["message"].lower()


@pytest.mark.asyncio
async def test_emergency_guard_exception_continues_in_paper():
    from agents.graph import _node_emergency

    state = {"mode": "PAPER_MODE", "errors": []}
    with patch("agents.graph.emergency_guard.evaluate", new=AsyncMock(side_effect=RuntimeError("test"))):
        out = await _node_emergency(state)

    assert "emergency" not in out or not (out.get("emergency") or {}).get("locked")
    assert "emergency_guard" in out["errors"][0]


def test_active_blocks_without_polygon_when_live_news_required():
    state = {
        "market_data": {"news_source": "mock", "data_quality": {}},
        "account": {"available": True},
    }
    ok, reason = validate_active_data(state, "ACTIVE")
    assert ok is False
    assert "Live news required" in reason

    status = active_data_status(state, "ACTIVE")
    assert status["active_blocked"] is True
    assert status["active_require_live_news"] is True
    assert "news" in status["block_reason"].lower()
