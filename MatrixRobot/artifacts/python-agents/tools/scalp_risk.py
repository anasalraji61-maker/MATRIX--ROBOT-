"""V11 scalping-specific risk gates — separate from V10 intraday risk."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from config import get_settings
from tools import memory
from tools.prop_time import prop_server_today
from tools.scalping_guard import scalping_asset_allowed
from tools.symbol_specs import pip_size_for


def _scalp_state() -> dict:
    today = prop_server_today()
    raw = memory.retrieve("scalp_daily_stats") or {}
    if raw.get("date") != today:
        return {"date": today, "trades_opened": 0, "shadow_signals": 0, "wins": 0, "losses": 0}
    return raw


def _save_scalp_state(stats: dict) -> None:
    memory.store("scalp_daily_stats", stats, ttl_seconds=86400 * 2)


def count_scalp_open() -> int:
    positions = memory.retrieve("open_positions") or []
    return sum(1 for p in positions if str(p.get("trade_tier") or "").upper() == "SCALP")


def scalp_trades_today() -> int:
    return int(_scalp_state().get("trades_opened", 0))


def compute_scalp_sizing(symbol: str, signal: str, settings=None) -> dict:
    """Tight SL/TP in pips for scalp trades."""
    s = settings or get_settings()
    pip = pip_size_for(symbol)
    sl_pips = int((float(s.scalping_sl_pips_min) + float(s.scalping_sl_pips_max)) / 2)
    tp_pips = int((float(s.scalping_tp_pips_min) + float(s.scalping_tp_pips_max)) / 2)
    rr = round(tp_pips / max(sl_pips, 1), 2)
    base_risk = float(s.max_risk_per_trade_pct) * float(s.scalping_risk_multiplier)
    return {
        "symbol": symbol,
        "signal": signal,
        "sl_pips": sl_pips,
        "tp_pips": tp_pips,
        "rr": rr,
        "risk_pct": round(base_risk, 4),
        "trade_tier": "SCALP",
        "max_hold_minutes": int(s.scalping_max_hold_minutes),
        "pip_size": pip,
    }


def approve_candidates(
    candidates: list[dict],
    state: dict,
    settings=None,
) -> dict[str, Any]:
    s = settings or get_settings()
    mode = state.get("mode") or s.trading_state
    approved: list[dict] = []
    rejected: dict[str, str] = {}

    if scalp_trades_today() >= int(s.scalping_max_trades_per_day):
        return {
            "scalping_approved": [],
            "scalping_rejected_reasons": {"_global": "daily scalp trade cap reached"},
        }

    open_scalp = count_scalp_open()
    slots = max(0, int(s.scalping_max_open_trades) - open_scalp)
    existing = list(memory.retrieve("open_positions") or [])
    quotes = (state.get("market_data") or {}).get("quotes", [])
    quote_map = {q["symbol"]: q for q in quotes}
    pending_for_exposure: list[dict] = list(existing)

    for c in candidates:
        sym = c["symbol"]
        signal = str(c.get("signal", "HOLD")).upper()
        if signal not in ("BUY", "SELL"):
            rejected[sym] = "not BUY/SELL"
            continue
        if not scalping_asset_allowed(sym, s):
            rejected[sym] = "asset not allowed for scalping"
            continue
        strength = float(c.get("strength") or 0)
        council = c.get("council") or {}
        if council and not council.get("approved"):
            rejected[sym] = f"council rejected meta={council.get('meta_score')}"
            continue
        sizing = compute_scalp_sizing(sym, signal, s)
        from tools.surgical_filters import check_entry_gates
        gate_ok, gate_reason = check_entry_gates(
            sym, strength, float(sizing.get("rr") or 0), settings=s, trade_tier="SCALP",
        )
        if not gate_ok:
            rejected[sym] = gate_reason
            continue
        if len(approved) >= slots:
            rejected[sym] = "max open scalp trades reached"
            continue

        from tools.data_quality import symbol_quarantine_reason
        from tools.liquidity_guard import check_spread
        from tools import correlation
        from tools.currency_exposure import check_exposure_allowed

        dq = symbol_quarantine_reason(sym, state, mode)
        if dq:
            rejected[sym] = f"quarantine: {dq}"
            continue
        spread_ok, spread_reason = check_spread(sym, quote_map.get(sym), s)
        if not spread_ok:
            rejected[sym] = spread_reason
            continue
        if getattr(s, "correlation_guard_enabled", True):
            report = correlation.build_report(pending_for_exposure)
            blocked, corr_reason = correlation.is_blocked(sym, signal, report)
            if blocked:
                rejected[sym] = f"correlation: {corr_reason}"
                continue
        exp_ok, exp_reason = check_exposure_allowed(sym, signal, pending_for_exposure, s)
        if not exp_ok:
            rejected[sym] = f"exposure: {exp_reason}"
            continue

        approved.append({**c, "sizing": sizing, "trade_tier": "SCALP"})
        pending_for_exposure.append({"symbol": sym, "action": signal, "trade_tier": "SCALP"})

    from tools.currency_exposure import build_exposure_report
    exposure = build_exposure_report(pending_for_exposure)
    blocked_corr = [
        sym for sym, reason in rejected.items()
        if "correlation" in reason or "exposure" in reason
    ]

    return {
        "scalping_approved": approved,
        "scalping_rejected_reasons": rejected,
        "exposure_by_currency": exposure.get("exposure_by_currency", {}),
        "blocked_by_correlation": blocked_corr,
    }


def record_scalp_open() -> None:
    stats = _scalp_state()
    stats["trades_opened"] = int(stats.get("trades_opened", 0)) + 1
    stats["last_open_at"] = datetime.now(timezone.utc).isoformat()
    _save_scalp_state(stats)


def record_shadow_signal() -> None:
    stats = _scalp_state()
    stats["shadow_signals"] = int(stats.get("shadow_signals", 0)) + 1
    _save_scalp_state(stats)
