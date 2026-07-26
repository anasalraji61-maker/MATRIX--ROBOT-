"""V11 Scalping Engine — funnel: 55 cheap → top 10 deep → council → risk → shadow/advisory/enforce."""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from config import get_settings
from tools import memory
from tools.cheap_scanner import run_cheap_scan
from tools.scalp_risk import approve_candidates, record_scalp_open, record_shadow_signal
from tools.scalp_scanner import deep_scan_symbols
from tools.scalping_guard import scalping_effective_enabled
from tools.strategy_router import candidate_allowed, route_market_mode
from tools.trading_council import evaluate_batch

logger = logging.getLogger("matrix.scalp_engine")

_last_report: dict[str, Any] = {}


def get_last_scalp_report() -> dict[str, Any]:
    cached = memory.retrieve("scalp_last_report")
    return cached or _last_report or {}


def _persist_report(report: dict) -> None:
    global _last_report
    report["updated_at"] = datetime.now(timezone.utc).isoformat()
    _last_report = report
    memory.store("scalp_last_report", report, ttl_seconds=86400 * 3)


async def run_scalp_pipeline(state: dict) -> dict[str, Any]:
    settings = get_settings()
    mode = state.get("mode") or settings.trading_state
    enabled, disable_reason = scalping_effective_enabled(mode, settings)

    base: dict[str, Any] = {
        "scalping_enabled": enabled,
        "scalping_mode": settings.scalping_mode,
        "scalping_disabled_reason": disable_reason if not enabled else "",
        "scanned_symbols_count": 0,
        "scalping_candidates_count": 0,
        "top_scalping_candidates": [],
        "scalping_approved": [],
        "scalping_rejected_reasons": {},
        "scalp_trades_opened": 0,
        "shadow_logged": 0,
    }

    if not enabled:
        _persist_report(base)
        return base

    route = route_market_mode(settings, state.get("session_profile"))
    base["strategy_route"] = route

    from tools.universe_manager import is_full_power
    from tools.preliminary_scorer import rank_all_symbols

    if is_full_power(settings):
        ranked = rank_all_symbols(state)
        base["scanned_symbols_count"] = len(state.get("symbols_analyzed") or [])
        deep_syms = [r["symbol"] for r in ranked[: int(settings.deep_analysis_top_n)]]
        base["cheap_ranked_top5"] = ranked[:5]
    else:
        cheap = run_cheap_scan(state)
        base["scanned_symbols_count"] = cheap.get("scanned_symbols_count", 0)
        base["cheap_ranked_top5"] = (cheap.get("cheap_ranked") or [])[:5]
        deep_syms = cheap.get("top_deep_symbols") or []

    if not deep_syms:
        base["scalping_rejected_reasons"] = {"_pipeline": "no symbols passed cheap scan"}
        _persist_report(base)
        return base

    session_kz = route.get("active_killzone", "")
    deep = await deep_scan_symbols(deep_syms, state, session_kz=session_kz)
    candidates = deep.get("top_scalping_candidates") or []
    base["scalping_candidates_count"] = deep.get("scalping_candidates_count", 0)
    base["top_scalping_candidates"] = candidates
    base["scalp_deep_rejected"] = deep.get("scalp_deep_rejected", {})

    filtered: list[dict] = []
    router_rejects: dict[str, str] = {}
    for c in candidates:
        ok, reason = candidate_allowed(c, route)
        if ok:
            filtered.append(c)
        else:
            router_rejects[c["symbol"]] = reason
    base["router_rejected"] = router_rejects

    council_result = evaluate_batch(state, filtered, settings)
    base["council"] = {
        "enabled": council_result.get("council_enabled"),
        "approved_count": len(council_result.get("approved") or []),
        "rejected": council_result.get("rejected") or [],
    }

    to_risk = council_result.get("approved") or filtered[: int(settings.council_top_candidates)]
    risk_out = approve_candidates(to_risk, state, settings)
    approved = risk_out.get("scalping_approved") or []
    rejected = {**router_rejects, **(risk_out.get("scalping_rejected_reasons") or {})}
    base["scalping_approved"] = approved
    base["scalping_rejected_reasons"] = rejected
    base["exposure_by_currency"] = risk_out.get("exposure_by_currency", {})
    base["blocked_by_correlation"] = risk_out.get("blocked_by_correlation", [])

    scalp_mode = str(settings.scalping_mode or "shadow").lower()
    opened = 0

    if scalp_mode == "shadow":
        for _ in approved:
            record_shadow_signal()
        base["shadow_logged"] = len(approved)
        base["execution_note"] = f"shadow — {len(approved)} signal(s) logged, no orders"
    elif scalp_mode == "advisory":
        base["shadow_logged"] = len(approved)
        base["execution_note"] = f"advisory — {len(approved)} signal(s); Telegram alert only"
        try:
            from tools import telegram_alerts
            if settings.has_telegram and approved:
                lines = ["V11 Scalp Advisory"]
                for a in approved[:3]:
                    lines.append(
                        f"{a['symbol']} {a['signal']} {a.get('strategy')} "
                        f"str={a.get('strength', 0):.2f}"
                    )
                await telegram_alerts.send("\n".join(lines), level="info")
        except Exception as e:
            logger.debug("scalp advisory telegram failed: %s", e)
    elif scalp_mode == "enforce" and mode in ("ACTIVE", "PAPER_MODE"):
        if mode == "PAPER_MODE":
            base["execution_note"] = f"enforce skipped — PAPER_MODE ({len(approved)} approved)"
        else:
            opened = await _execute_scalp_batch(approved, state, settings)
            base["scalp_trades_opened"] = opened
            base["execution_note"] = f"enforce — {opened}/{len(approved)} filled"
    else:
        base["execution_note"] = f"mode={scalp_mode} — no execution"

    _persist_report(base)
    return base


async def _execute_scalp_batch(approved: list[dict], state: dict, settings) -> int:
    """Execute scalp trades — separate path but same V10 protection gates."""
    if not approved:
        return 0
    from agents.execution_agent import _execute_one
    from tools import memory, account_state
    from tools.scalp_execution_guard import preflight_batch, preflight_trade, exposure_snapshot

    mode = state.get("mode") or settings.trading_state
    batch_ok, batch_reason = await preflight_batch(state, mode, settings)
    if not batch_ok:
        logger.warning("scalp batch blocked: %s", batch_reason)
        return 0

    filled = 0
    existing = list(memory.retrieve("open_positions") or [])
    rejections: dict[str, str] = {}
    quotes = (state.get("market_data") or {}).get("quotes", [])
    quote_map = {q["symbol"]: q for q in quotes}

    for a in approved:
        sym = a["symbol"]
        act = str(a["signal"]).upper()
        ok, reason = preflight_trade(a, state, mode, existing, settings)
        if not ok:
            rejections[sym] = reason
            continue
        sizing_meta = a.get("sizing") or {}
        ind = (state.get("indicators") or {}).get(sym, {})
        atr = float(ind.get("atr_14") or 0.001) or 0.001
        from tools.risk_sizing import compute_safe_sizing
        from tools.surgical_filters import xagusd_risk_multiplier

        acct = state.get("account") or {}
        equity = float(acct.get("equity") or acct.get("balance") or 10000)
        starting = float(acct.get("starting_balance") or equity)
        sizing = compute_safe_sizing(
            symbol=sym,
            strength=float(a.get("strength") or 0.7),
            atr=atr,
            settings=settings,
            equity=equity,
            starting_balance=starting,
            current_open_risk_pct=0.0,
            prop_status=state.get("prop_status"),
            vol_mult=0.5 * xagusd_risk_multiplier(sym, settings),
            max_risk_pct_override=sizing_meta.get("risk_pct"),
            trade_tier="SCALP",
            session_profile=state.get("session_profile"),
        )
        if sizing.get("rejected"):
            continue
        sizing["sl_pips"] = int(sizing_meta.get("sl_pips") or sizing.get("sl_pips") or 5)
        sizing["tp_pips"] = int(sizing_meta.get("tp_pips") or sizing.get("tp_pips") or 7)
        sizing["rr"] = float(sizing_meta.get("rr") or sizing.get("rr") or 1.2)

        try:
            res = await _execute_one(sym, act, sizing, state, settings, mode)
            if res.executed:
                filled += 1
                record_scalp_open()
                existing.append({
                    "trade_id": res.trade_id,
                    "symbol": res.symbol,
                    "action": res.action,
                    "lots": res.lots,
                    "entry_price": res.entry_price,
                    "stop_loss": res.stop_loss,
                    "take_profit": res.take_profit,
                    "initial_stop_loss": res.stop_loss,
                    "mode": res.mode,
                    "opened_at": res.timestamp,
                    "pnl": 0.0,
                    "trade_tier": "SCALP",
                    "strategy": a.get("strategy"),
                    "strategy_name": a.get("strategy"),
                    "scalp_strategy": a.get("strategy"),
                    "strength": float(a.get("strength") or 0),
                    "spread_at_entry": (quote_map.get(sym) or {}).get("spread_pips"),
                    "spread_pips": (quote_map.get(sym) or {}).get("spread_pips"),
                    "council_approved": (a.get("council") or {}).get("approved"),
                    "council_meta_score": (a.get("council") or {}).get("meta_score"),
                })
        except Exception as e:
            logger.warning("scalp execute %s failed: %s", sym, e)

    if filled:
        memory.store("open_positions", existing)
        if mode == "ACTIVE":
            await account_state.sync_open_positions()
    if rejections:
        memory.store("scalp_execution_rejections", rejections, ttl_seconds=86400)
    return filled
