"""Per-trade risk approval batch — Phase 6."""
from __future__ import annotations

from dataclasses import asdict

from config import get_settings
from models.schemas import RiskAssessment
from tools import memory, correlation, economic_calendar, prop_rules, account_state
from tools import adaptive_policy as _ape
from tools import trade_tiers, position_reconciler
from tools.data_quality import compute_data_quarantine, symbol_quarantine_reason, validate_active_data
from tools.liquidity_guard import check_spread
from tools.risk_sizing import compute_safe_sizing, _FALLBACK_EQUITY
from tools.session_engine import check_symbol_session_allowed
from tools.off_session_limits import is_off_session, asset_allowed_off_session, trades_today_count
from tools.session_24h import is_24h_all_systems
from agents.supervisor_agent import build_approved_trades


def _reject_state(state: dict, reason: str, prop_dump: dict, daily_dd: float, total_dd: float) -> dict:
    assessment = RiskAssessment(
        approved=False,
        reason=reason,
        position_size_lots=0.0,
        stop_loss_pips=0,
        take_profit_pips=0,
        risk_reward_ratio=0.0,
        current_daily_drawdown_pct=daily_dd,
        current_total_drawdown_pct=total_dd,
    )
    return {
        **state,
        "risk": assessment.model_dump(),
        "approved_risk_trades": [],
        "prop_status": prop_dump,
    }


def _build_rejection_report(
    rejections: dict[str, list[str]],
    quarantine: dict,
    session_blocked: dict[str, list[str]],
    off_session_candidates: list[dict],
) -> dict:
    return {
        "symbols": rejections,
        "total_rejected": sum(len(v) for v in rejections.values()),
        "data_quarantined_symbols": quarantine.get("data_quarantine_symbols", {}),
        "global_data_block": quarantine.get("global_data_block", False),
        "global_data_block_reason": quarantine.get("global_data_block_reason", ""),
        "session_blocked_symbols": session_blocked,
        "off_session_candidates": off_session_candidates,
    }


async def evaluate_candidates(state: dict) -> dict:
    settings = get_settings()
    mode = state.get("mode", settings.trading_state)

    if mode == "ACTIVE":
        bridge_ok = await position_reconciler.ensure_synced()
        if not bridge_ok:
            prop = await prop_rules.evaluate(state)
            return _reject_state(
                state,
                "MT5 state unknown — bridge unreachable, new trades blocked",
                asdict(prop),
                0.0,
                0.0,
            )

    quarantine = compute_data_quarantine(state, mode)
    state = {**state, "data_quarantine": quarantine}

    ok, dq_reason = validate_active_data(state, mode)
    if not ok:
        prop = await prop_rules.evaluate(state)
        acct = state.get("account") or {}
        report = _build_rejection_report({}, quarantine, {}, [])
        memory.store("risk_rejection_report", report, ttl_seconds=86400)
        return {
            **_reject_state(
                state,
                f"Data integrity gate: {dq_reason}",
                asdict(prop),
                float(acct.get("daily_drawdown_pct", 0.0) or 0.0),
                float(acct.get("total_drawdown_pct", 0.0) or 0.0),
            ),
            "risk_rejection_report": report,
        }

    acct = state.get("account") or {}
    equity = float(acct.get("equity") or _FALLBACK_EQUITY)
    starting = float(acct.get("starting_balance") or equity or _FALLBACK_EQUITY)
    daily_dd = float(acct.get("daily_drawdown_pct", 0.0) or 0.0)
    total_dd = float(acct.get("total_drawdown_pct", 0.0) or 0.0)

    prop = await prop_rules.evaluate(state)
    prop_dump = asdict(prop)

    if not prop.can_trade:
        return _reject_state(state, prop.block_reason or "Prop-firm guard active", prop_dump, daily_dd, total_dd)

    session = state.get("session_profile") or {}
    # Tiered mode: session checks are per-symbol (not whole-cycle block).

    skip, skip_reason = _ape.should_skip_session()
    if skip:
        return _reject_state(state, f"APE: session skipped — {skip_reason}", prop_dump, daily_dd, total_dd)

    analyses = state.get("analyses", [])
    candidates = build_approved_trades(analyses, settings)
    if not candidates:
        return _reject_state(state, "No actionable signals — standing aside", prop_dump, daily_dd, total_dd)

    existing = list(memory.retrieve("open_positions") or [])
    quotes = (state.get("market_data") or {}).get("quotes", [])
    quote_map = {q["symbol"]: q for q in quotes}
    cal_state = state.get("economic_calendar") or {}
    cal_affected = cal_state.get("affected_currencies", [])

    approved: list[dict] = []
    rejections: dict[str, list[str]] = {}
    session_blocked: dict[str, list[str]] = {}
    off_session_candidates: list[dict] = []
    cumulative_open_risk = prop_rules.open_risk_pct(existing, starting)
    profile = getattr(settings, "account_profile", "FN_CHALLENGE")
    is_funded = profile.upper() == "FN_FUNDED"
    off_sess = is_off_session(session, settings)

    def _record_reject(sym: str, reason: str) -> None:
        rejections.setdefault(sym, []).append(reason)

    for cand in candidates:
        sym = cand.symbol
        signal = cand.signal
        strength = cand.strength
        tier = trade_tiers.classify_trade_tier(strength, settings)
        reject_reason = None

        dq_reason = symbol_quarantine_reason(sym, state, mode)
        if dq_reason:
            reject_reason = f"Data quarantine: {dq_reason}"

        if not reject_reason:
            sess_ok, sess_reason, is_shadow = check_symbol_session_allowed(
                sym, tier, session, settings,
            )
            if not sess_ok:
                session_blocked.setdefault(sym, []).append(sess_reason)
                if is_shadow:
                    off_session_candidates.append({
                        "symbol": sym,
                        "signal": signal,
                        "strength": strength,
                        "trade_tier": tier,
                        "reason": sess_reason,
                    })
                reject_reason = f"Session filter: {sess_reason}"

        if not reject_reason and is_24h_all_systems(settings):
            if session.get("active_killzone") in ("none", "asian"):
                max_open = int(getattr(settings, "off_session_24h_max_open_trades", 4))
                max_day = int(getattr(settings, "off_session_24h_max_trades_per_day", 20))
                if len(existing) + len(approved) >= max_open:
                    reject_reason = f"24h off-session max open trades ({max_open})"
                elif account_state.trades_today_count() >= max_day:
                    reject_reason = f"24h daily trade cap ({max_day})"
                elif not asset_allowed_off_session(sym, settings):
                    reject_reason = "24h — asset not in allowed universe"
                elif getattr(settings, "off_session_require_no_news", True):
                    news_blocked, news_reason = prop_rules.check_news_blackout(
                        state, settings, profile, is_funded,
                    )
                    if news_blocked:
                        reject_reason = f"24h news gate: {news_reason}"

        if not reject_reason and session.get("session_filter_mode") == "extended":
            if not is_24h_all_systems(settings) and session.get("active_killzone") == "none" and tier == "SMALL":
                off_min = float(getattr(settings, "off_session_min_strength", 0.80))
                if strength < off_min:
                    reject_reason = (
                        f"Off-session gate: strength {strength:.2f} < {off_min:.2f}"
                    )
                elif not asset_allowed_off_session(sym, settings):
                    reject_reason = "Off-session — FX only"
                elif len(existing) + len(approved) >= int(
                    getattr(settings, "off_session_max_open_trades", 1)
                ):
                    reject_reason = "Off-session max open trades reached"
                elif trades_today_count() >= int(
                    getattr(settings, "off_session_max_trades_per_day", 2)
                ):
                    reject_reason = "Off-session daily trade cap reached"
                elif getattr(settings, "off_session_require_data_clean", True) and dq_reason:
                    reject_reason = f"Off-session data gate: {dq_reason}"
                elif getattr(settings, "off_session_require_no_news", True):
                    news_blocked, news_reason = prop_rules.check_news_blackout(
                        state, settings, profile, is_funded,
                    )
                    if news_blocked:
                        reject_reason = f"Off-session news gate: {news_reason}"

        if tier == "HOLD":
            reject_reason = reject_reason or f"Strength {strength:.2f} below tier minimum"
        elif len(existing) + len(approved) >= settings.max_concurrent_positions:
            reject_reason = reject_reason or f"Max concurrent positions ({settings.max_concurrent_positions})"
        elif tier == "SMALL":
            if account_state.count_small_open_positions(existing + approved) >= settings.small_trade_max_open:
                reject_reason = reject_reason or "Small-trade open cap reached"
            elif account_state.small_trades_today_count() >= settings.small_trade_max_per_day:
                reject_reason = reject_reason or "Small-trade daily cap reached"

        paused, pause_reason = _ape.is_symbol_paused(sym)
        if not reject_reason and paused:
            reject_reason = f"APE: {sym} paused — {pause_reason}"

        conviction_override = _ape.get_conviction_override()
        tier_floor = trade_tiers.min_candidate_strength(settings)
        effective_threshold = conviction_override if conviction_override else tier_floor
        if not reject_reason and strength < effective_threshold:
            reject_reason = f"Conviction gate: {strength:.2f} < {effective_threshold:.2f}"

        if not reject_reason and settings.economic_calendar_enabled:
            news_blocked, news_reason = prop_rules.check_news_blackout(
                state, settings, profile, is_funded,
            )
            if news_blocked and economic_calendar.symbol_affected(sym, cal_affected):
                reject_reason = news_reason

        if not reject_reason and settings.correlation_guard_enabled:
            corr_state = state.get("correlation_report")
            if corr_state:
                from models.schemas import CorrelationReport
                report = CorrelationReport(**corr_state)
            else:
                report = correlation.build_report(existing + approved)
            blocked, reason = correlation.is_blocked(sym, signal, report)
            if blocked:
                reject_reason = reason

        if not reject_reason:
            from tools.currency_exposure import check_exposure_allowed
            exp_ok, exp_reason = check_exposure_allowed(
                sym, signal, existing + approved, settings,
            )
            if not exp_ok:
                reject_reason = f"Exposure guard: {exp_reason}"

        spread_ok, spread_reason = check_spread(sym, quote_map.get(sym), settings)
        if not reject_reason and not spread_ok:
            reject_reason = f"Liquidity guard: {spread_reason}"

        if reject_reason:
            _record_reject(sym, reject_reason)
            continue

        ind = state.get("indicators", {}).get(sym, {})
        atr = ind.get("atr_14", 0.001) or 0.001
        vol_regimes = state.get("volatility_regimes", {}) if settings.volatility_regime_enabled else {}
        vol_mult = float((vol_regimes.get(sym) or {}).get("size_multiplier", 1.0))
        ape_multiplier = _ape.get_risk_multiplier()
        if off_sess and tier == "SMALL":
            ape_multiplier *= float(getattr(settings, "off_session_risk_multiplier", 0.15))
        if is_24h_all_systems(settings) and session.get("active_killzone") in ("none", "asian"):
            if tier == "NORMAL":
                ape_multiplier *= float(getattr(settings, "off_session_24h_risk_multiplier_normal", 0.35))
            elif tier == "SMALL":
                ape_multiplier *= float(getattr(settings, "off_session_24h_risk_multiplier_small", 0.20))
        tier_risk = trade_tiers.risk_pct_for_tier(tier, settings)

        sizing = compute_safe_sizing(
            symbol=sym,
            strength=strength,
            atr=atr,
            equity=equity,
            starting_balance=starting,
            current_open_risk_pct=cumulative_open_risk,
            prop_status=prop_dump,
            settings=settings,
            vol_mult=vol_mult,
            adaptive_risk_multiplier=ape_multiplier,
            max_risk_pct_override=tier_risk,
            trade_tier=tier,
            session_profile=session,
        )

        if sizing["rejected"]:
            _record_reject(sym, sizing.get("reject_reason") or sizing.get("cap_reason") or "sizing rejected")
            continue

        min_rr = trade_tiers.rr_minimum_for_tier(tier, settings)
        if off_sess and tier == "SMALL":
            min_rr = max(min_rr, float(getattr(settings, "off_session_min_rr", 1.8)))
        if float(sizing.get("rr") or 0) < min_rr:
            _record_reject(sym, f"R/R {sizing.get('rr')} < {min_rr}")
            continue

        from tools.surgical_filters import check_entry_gates
        gate_ok, gate_reason = check_entry_gates(
            sym, strength, float(sizing.get("rr") or 0), settings=settings, trade_tier=tier,
        )
        if not gate_ok:
            _record_reject(sym, gate_reason)
            continue

        entry = {
            "symbol": sym,
            "signal": signal,
            "direction": signal,
            "strength": strength,
            "trade_tier": tier,
            "approved": True,
            "lots": sizing["lots"],
            "stop_loss_pips": sizing["sl_pips"],
            "take_profit_pips": sizing["tp_pips"],
            "risk_usd": sizing["risk_usd"],
            "risk_percent": sizing["risk_pct_of_starting"],
            "risk_reward_ratio": sizing["rr"],
            "sizing": sizing,
            "reason": (
                f"Approved {sizing['lots']} lots — risk ${sizing['risk_usd']:.2f} "
                f"({sizing['risk_pct_of_starting']:.2f}%) bound by {sizing['cap_reason']}"
            ),
        }
        approved.append(entry)
        cumulative_open_risk += sizing["risk_pct_of_starting"]

    report = _build_rejection_report(
        rejections, quarantine, session_blocked, off_session_candidates,
    )
    from tools.currency_exposure import build_exposure_report
    report["exposure_by_currency"] = build_exposure_report(existing + approved).get(
        "exposure_by_currency", {},
    )
    report["blocked_by_correlation"] = [
        sym for sym, reasons in rejections.items()
        if any("correlation" in r.lower() for r in reasons)
    ]

    if not approved:
        memory.store("risk_rejection_report", report, ttl_seconds=86400)
        reason = "No candidates passed per-trade risk gates"
        if off_session_candidates and not rejections:
            reason = (
                f"Session shadow — {len(off_session_candidates)} candidate(s) "
                "blocked outside killzone (see off_session_candidates)"
            )
        return {
            **_reject_state(state, reason, prop_dump, daily_dd, total_dd),
            "risk_rejection_report": report,
        }

    top = approved[0]
    sz = top["sizing"]
    assessment = RiskAssessment(
        approved=True,
        reason=top["reason"],
        position_size_lots=sz["lots"],
        stop_loss_pips=sz["sl_pips"],
        take_profit_pips=sz["tp_pips"],
        risk_reward_ratio=sz["rr"],
        current_daily_drawdown_pct=daily_dd,
        current_total_drawdown_pct=total_dd,
    )
    return {
        **state,
        "risk": assessment.model_dump(),
        "approved_risk_trades": approved,
        "prop_status": prop_dump,
        "risk_rejection_report": report,
    }
