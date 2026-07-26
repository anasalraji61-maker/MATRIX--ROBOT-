"""
Risk Agent — per-trade batch approval (Phase 6).

Sizing helpers live in tools.risk_sizing (re-exported here for compatibility).
"""
from tools.risk_sizing import (
    PIP_VALUE,
    pip_size_for,
    compute_safe_sizing,
    _FALLBACK_EQUITY,
)


async def run(state: dict) -> dict:
    from tools.risk_batch import evaluate_candidates
    return await evaluate_candidates(state)
