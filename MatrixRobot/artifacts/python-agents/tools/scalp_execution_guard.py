"""Scalp execution preflight — same V10 protections before bypass-path fills."""
from __future__ import annotations

from typing import Any

from config import get_settings
from tools import memory, correlation, account_state
from tools.currency_exposure import check_exposure_allowed, build_exposure_report
from tools.data_quality import symbol_quarantine_reason
from tools.emergency_guard import is_daily_locked
from tools.liquidity_guard import check_spread


async def preflight_batch(state: dict, mode: str, settings=None) -> tuple[bool, str]:
    """Batch-level gates before any scalp order."""
    s = settings or get_settings()

    if is_daily_locked():
        return False, "emergency daily lockout active"

    if mode == "ACTIVE":
        from tools.bridge_manual import is_blocking
        if is_blocking():
            return False, "bridge manual_check_required — execution blocked"

        from tools import circuit_status
        pre = await circuit_status.preflight_cycle(mode)
        if not pre.get("can_run"):
            return False, pre.get("message", "circuit preflight blocked")

        from tools import position_reconciler
        if not await position_reconciler.ensure_synced():
            return False, "MT5 bridge unreachable — scalp blocked"

    prop = state.get("prop_status") or {}
    if prop and not prop.get("can_trade", True):
        return False, f"prop guard: {prop.get('block_reason', 'blocked')}"

    risk = state.get("risk") or {}
    daily_dd = float(risk.get("current_daily_drawdown_pct") or 0)
    if daily_dd >= float(getattr(s, "max_daily_drawdown_pct", 4.0)):
        return False, f"daily drawdown {daily_dd:.2f}% >= cap"

    return True, ""


def preflight_trade(
    candidate: dict,
    state: dict,
    mode: str,
    existing_positions: list[dict] | None = None,
    settings=None,
) -> tuple[bool, str]:
    """Per-trade V10-style gates for scalp path."""
    s = settings or get_settings()
    sym = candidate["symbol"]
    signal = str(candidate.get("signal", "HOLD")).upper()
    existing = list(existing_positions or memory.retrieve("open_positions") or [])

    dq = symbol_quarantine_reason(sym, state, mode)
    if dq:
        return False, f"data quarantine: {dq}"

    quotes = (state.get("market_data") or {}).get("quotes", [])
    quote_map = {q["symbol"]: q for q in quotes}
    spread_ok, spread_reason = check_spread(sym, quote_map.get(sym), s)
    if not spread_ok:
        return False, spread_reason

    if s.correlation_guard_enabled:
        report = correlation.build_report(existing)
        blocked, reason = correlation.is_blocked(sym, signal, report)
        if blocked:
            return False, reason

    exp_ok, exp_reason = check_exposure_allowed(sym, signal, existing, s)
    if not exp_ok:
        return False, f"exposure: {exp_reason}"

    open_scalp = sum(1 for p in existing if str(p.get("trade_tier", "")).upper() == "SCALP")
    if open_scalp >= int(s.scalping_max_open_trades):
        return False, f"scalp open cap ({s.scalping_max_open_trades})"

    if len(existing) >= int(s.max_concurrent_positions):
        return False, f"max concurrent ({s.max_concurrent_positions})"

    if account_state.trades_today_count() >= int(s.max_trades_per_day):
        return False, f"daily trade cap ({s.max_trades_per_day})"

    sizing = candidate.get("sizing") or {}
    if s.require_stop_loss and int(sizing.get("sl_pips") or 0) <= 0:
        return False, "mandatory SL missing"

    return True, ""


def exposure_snapshot(positions: list[dict] | None = None) -> dict:
    pos = positions or memory.retrieve("open_positions") or []
    return build_exposure_report(pos)
