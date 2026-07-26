"""Supervisor ↔ Execution alignment (Phase 1.1)."""
from agents.supervisor_agent import build_approved_trades, _decision_from_approved
from models.schemas import ApprovedTrade


class _Settings:
    max_concurrent_positions = 3
    min_conviction_threshold = 0.55
    normal_trade_min_strength = 0.60
    small_trade_min_strength = 0.50
    enable_small_trades = True
    max_risk_per_trade_pct = 0.8
    small_trade_max_risk_pct = 0.4


def test_build_approved_trades_ranks_and_caps():
    analyses = [
        {"symbol": "EURUSD", "signal": "BUY", "strength": 0.72},
        {"symbol": "GBPUSD", "signal": "BUY", "strength": 0.81},
        {"symbol": "USDJPY", "signal": "SELL", "strength": 0.65},
        {"symbol": "XAUUSD", "signal": "BUY", "strength": 0.48},
        {"symbol": "AUDUSD", "signal": "HOLD", "strength": 0.90},
    ]
    approved = build_approved_trades(analyses, _Settings())
    assert len(approved) == 3
    assert [t.symbol for t in approved] == ["GBPUSD", "EURUSD", "USDJPY"]


def test_decision_from_approved_lists_all():
    approved = [
        ApprovedTrade(symbol="GBPUSD", signal="BUY", strength=0.81),
        ApprovedTrade(symbol="EURUSD", signal="BUY", strength=0.72),
    ]
    d = _decision_from_approved(approved, "test", "dd ok")
    assert d.action == "BUY"
    assert d.symbol == "GBPUSD"
    assert len(d.approved_trades) == 2
    assert "Approved 2 trade(s)" in d.reasoning
