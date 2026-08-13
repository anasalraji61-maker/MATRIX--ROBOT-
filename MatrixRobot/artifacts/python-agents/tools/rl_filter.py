"""RL filter — contextual bandit gate on supervisor-approved trades."""
from __future__ import annotations

import logging
from typing import Any

from ml.rl.policy import get_policy
from models.schemas import ApprovedTrade

logger = logging.getLogger("matrix.rl_filter")


def filter_trades(
    approved: list[ApprovedTrade],
    state: dict,
    settings,
) -> tuple[list[ApprovedTrade], list[dict[str, Any]]]:
    if not approved or not getattr(settings, "rl_enabled", False):
        return approved, []

    policy = get_policy(settings)
    scores: list[dict[str, Any]] = []
    kept: list[ApprovedTrade] = []
    min_q = float(getattr(settings, "rl_min_q_value", -0.15))
    mode = (getattr(settings, "rl_mode", "shadow") or "shadow").lower()

    for trade in approved:
        sc = policy.score(trade.symbol, trade.signal)
        scores.append(sc)
        if sc.get("explore"):
            kept.append(trade)
            continue
        q = float(sc.get("q_value", 0.0))
        if q >= min_q:
            kept.append(trade)
        else:
            logger.info(
                "RL filter blocked %s %s — q=%.3f < %.3f (mode=%s)",
                trade.symbol, trade.signal, q, min_q, mode,
            )

    if mode == "shadow":
        return approved, scores

    return kept, scores


def record_trade_close(symbol: str, signal: str, pnl: float, settings=None) -> dict | None:
    from config import get_settings

    s = settings or get_settings()
    if not getattr(s, "rl_enabled", False):
        return None
    sig = (signal or "").upper()
    if sig not in ("BUY", "SELL"):
        return None
    return get_policy(s).record_outcome(symbol, sig, float(pnl or 0.0))


def get_status(settings=None) -> dict[str, Any]:
    from config import get_settings

    s = settings or get_settings()
    if not getattr(s, "rl_enabled", False):
        return {"enabled": False}
    policy = get_policy(s)
    top_arms = sorted(policy.q.items(), key=lambda x: x[1], reverse=True)[:10]
    bottom_arms = sorted(policy.q.items(), key=lambda x: x[1])[:5]
    return {
        "enabled": True,
        "mode": getattr(s, "rl_mode", "shadow"),
        "min_q_value": getattr(s, "rl_min_q_value", -0.15),
        "learning_rate": getattr(s, "rl_learning_rate", 0.12),
        "total_updates": policy.total_updates,
        "arms_tracked": len(policy.q),
        "top_arms": [{"arm": k, "q": v, "n": policy.n.get(k, 0)} for k, v in top_arms],
        "bottom_arms": [{"arm": k, "q": v, "n": policy.n.get(k, 0)} for k, v in bottom_arms],
        "policy_file": str(policy.__class__.__module__),
    }
