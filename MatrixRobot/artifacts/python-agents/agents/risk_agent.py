"""
Risk Agent — enforces both:
  • Internal stricter targets (config.max_daily_drawdown_pct, etc.)
  • FundedNext (or other prop firm) hard caps via tools.prop_rules
  • Per-trade Kelly sizing using LIVE equity from MT5 bridge
  • Total open risk guard (sum of all open SL distances)
  • Correlation + economic-calendar veto
Rejects trades when any guard fires.
"""
from config import get_settings
from models.schemas import RiskAssessment
from tools import memory, correlation, economic_calendar, prop_rules
from tools import adaptive_policy as _ape


# Pip values (approximate, USD-denominated). Used by execution_agent and
# prop_rules.open_risk_pct as well — keep exported.
PIP_VALUE = {
    "EURUSD": 10.0, "GBPUSD": 10.0, "AUDUSD": 10.0, "NZDUSD": 10.0,
    "USDCHF": 11.0, "USDCAD": 7.5, "USDJPY": 6.7,
    "EURGBP": 13.0, "EURJPY": 6.7, "GBPJPY": 6.7, "AUDJPY": 6.7,
    "CHFJPY": 6.7, "CADJPY": 6.7, "NZDJPY": 6.7,
    "EURAUD": 7.5, "EURCHF": 11.0, "GBPCHF": 11.0,
    "AUDCAD": 7.5, "AUDNZD": 7.0,
    "XAUUSD": 1.0, "XAGUSD": 5.0,
}

# Fallback used only if MT5 bridge is offline AND no starting balance has
# ever been snapshotted. Kept conservative.
_FALLBACK_EQUITY = 10_000.0


def pip_size_for(symbol: str) -> float:
    """Pip size in price units. Shared by sizing helpers."""
    if symbol == "XAUUSD":
        return 0.10
    if symbol == "XAGUSD":
        return 0.001
    if "JPY" in symbol:
        return 0.01
    if symbol.isalpha() and len(symbol) <= 5 and not any(
        c in symbol for c in ("USD", "EUR", "GBP", "JPY", "CHF", "AUD", "NZD", "CAD")
    ):
        return 0.01
    return 0.0001


def compute_safe_sizing(
    symbol: str,
    strength: float,
    atr: float,
    equity: float,
    starting_balance: float,
    current_open_risk_pct: float,
    prop_status: dict | None,
    settings,
    vol_mult: float = 1.0,
    adaptive_risk_multiplier: float = 1.0,
) -> dict:
    """Compute (lots, SL, TP) such that the trade's max loss respects ALL of:
        1. Per-trade cap : equity × max_risk_per_trade_pct × strength
        2. Daily DD room : (max_daily_drawdown_pct - current_daily_dd - safety) × starting
        3. Total DD room : (max_total_drawdown_pct - current_total_dd - safety) × starting
        4. Portfolio room: (max_total_open_risk_pct - current_open_risk_pct)  × starting

    The binding constraint (smallest of the four) sets the USD budget.
    Lots are derived from that budget given an ATR-based SL distance.

    Returns dict containing lots, sl_pips, tp_pips, rr, pip, pip_val,
    risk_usd, risk_pct_of_starting, budget_usd, budget_pct, cap_reason,
    rejected, reject_reason.

    `rejected=True` means: no room left, OR even minimum lot (0.01) would
    risk more than the budget allows — the trade MUST NOT be opened.
    """
    pip = pip_size_for(symbol)
    sl_pips = max(int(atr * (1.0 / pip) * 1.5), 15)
    tp_pips = max(int(sl_pips * 2.0), 30)
    pip_val = PIP_VALUE.get(symbol, 10.0)
    rr = round(tp_pips / max(sl_pips, 1), 2)

    safety = float(getattr(settings, "sizing_safety_buffer_pct", 0.3))
    ps = prop_status or {}
    daily_dd_now = float(ps.get("daily_loss_pct", 0.0) or 0.0)
    total_dd_now = float(ps.get("total_loss_pct", 0.0) or 0.0)

    eq = max(equity, 1.0)
    sb = max(starting_balance, 1.0)

    # Each cap converted to a USD budget separately. Per-trade scales with
    # LIVE equity (the spec); the three DD/portfolio caps scale with
    # STARTING balance (matches FundedNext's denominator).
    # adaptive_risk_multiplier (0.3–1.0): applied by brain via APE to shrink
    # position sizes after losses or bad market conditions. Never above 1.0.
    ape_mult = max(0.3, min(float(adaptive_risk_multiplier or 1.0), 1.0))
    per_trade_usd      = eq * (settings.max_risk_per_trade_pct / 100.0) * min(strength, 1.0) * ape_mult
    daily_room_usd     = sb * max(0.0, settings.max_daily_drawdown_pct - daily_dd_now - safety) / 100.0
    total_room_usd     = sb * max(0.0, settings.max_total_drawdown_pct - total_dd_now - safety) / 100.0
    portfolio_room_usd = sb * max(0.0, settings.max_total_open_risk_pct - current_open_risk_pct) / 100.0

    caps_usd = [
        (per_trade_usd,      "per-trade cap"),
        (daily_room_usd,     "daily DD buffer to internal target"),
        (total_room_usd,     "total DD buffer to internal target"),
        (portfolio_room_usd, "portfolio open-risk cap"),
    ]
    risk_budget_usd, cap_reason = min(caps_usd, key=lambda c: c[0])
    binding_pct = (risk_budget_usd / sb) * 100.0

    # No room → reject before any lot math
    if risk_budget_usd <= 0.0:
        return {
            "lots": 0.0, "sl_pips": sl_pips, "tp_pips": tp_pips, "rr": rr,
            "pip": pip, "pip_val": pip_val,
            "risk_usd": 0.0, "risk_pct_of_starting": 0.0,
            "budget_usd": 0.0, "budget_pct": 0.0,
            "cap_reason": cap_reason, "rejected": True,
            "reject_reason": f"No room left under '{cap_reason}' (daily {daily_dd_now:.2f}%, total {total_dd_now:.2f}%, open {current_open_risk_pct:.2f}%)",
        }

    # Minimum-lot check FIRST: would even 0.01 lots (the broker minimum)
    # breach the budget? STRICT: no tolerance. If yes the trade must NEVER
    # be sent — there is no safe lot size below 0.01.
    risk_at_min_lot_usd = sl_pips * pip_val * 0.01
    if risk_at_min_lot_usd > risk_budget_usd:
        return {
            "lots": 0.0, "sl_pips": sl_pips, "tp_pips": tp_pips, "rr": rr,
            "pip": pip, "pip_val": pip_val,
            "risk_usd": 0.0, "risk_pct_of_starting": 0.0,
            "budget_usd": round(risk_budget_usd, 2),
            "budget_pct": round(binding_pct, 3),
            "cap_reason": cap_reason, "rejected": True,
            "reject_reason": (
                f"Minimum lot 0.01 would risk ${risk_at_min_lot_usd:.2f} "
                f"> budget ${risk_budget_usd:.2f} under '{cap_reason}'"
            ),
        }

    # Volatility regime: only SHRINK in high-vol (clamped to ≤1.0) so it
    # can never raise actual risk above the binding cap. Calm-market upsize
    # is intentionally disabled here for compliance safety.
    raw_lots = risk_budget_usd / max(sl_pips * pip_val, 1.0)
    raw_lots = raw_lots * max(0.1, min(vol_mult, 1.0))
    lots = round(max(0.01, min(raw_lots, 5.0)), 2)

    # Safety net: re-derive risk and shrink lots if rounding nudged us over
    # the budget (e.g. round-up at the second decimal).
    actual_risk_usd = sl_pips * pip_val * lots
    if actual_risk_usd > risk_budget_usd and lots > 0.01:
        lots = max(0.01, round((risk_budget_usd / max(sl_pips * pip_val, 1.0)) - 0.005, 2))
        actual_risk_usd = sl_pips * pip_val * lots

    actual_risk_pct = (actual_risk_usd / sb) * 100.0

    # Final hard assertion: under no circumstance allow risk > budget.
    # This catches any pathological rounding edge case not handled above.
    if actual_risk_usd > risk_budget_usd:
        return {
            "lots": 0.0, "sl_pips": sl_pips, "tp_pips": tp_pips, "rr": rr,
            "pip": pip, "pip_val": pip_val,
            "risk_usd": 0.0, "risk_pct_of_starting": 0.0,
            "budget_usd": round(risk_budget_usd, 2),
            "budget_pct": round(binding_pct, 3),
            "cap_reason": cap_reason, "rejected": True,
            "reject_reason": (
                f"Final guard: risk ${actual_risk_usd:.2f} > budget "
                f"${risk_budget_usd:.2f} under '{cap_reason}'"
            ),
        }

    return {
        "lots": lots, "sl_pips": sl_pips, "tp_pips": tp_pips, "rr": rr,
        "pip": pip, "pip_val": pip_val,
        "risk_usd": round(actual_risk_usd, 2),
        "risk_pct_of_starting": round(actual_risk_pct, 3),
        "budget_usd": round(risk_budget_usd, 2),
        "budget_pct": round(binding_pct, 3),
        "cap_reason": cap_reason,
        "rejected": False,
        "reject_reason": "",
    }


async def run(state: dict) -> dict:
    settings = get_settings()
    best = state.get("best_analysis", {})
    signal = best.get("signal", "HOLD")
    symbol = best.get("symbol", "")
    strength = best.get("strength", 0.0)

    # ── Live account snapshot (populated by data_agent) ──────────────
    acct = state.get("account") or {}
    equity = float(acct.get("equity") or _FALLBACK_EQUITY)
    starting = float(acct.get("starting_balance") or equity or _FALLBACK_EQUITY)
    daily_dd = float(acct.get("daily_drawdown_pct", 0.0) or 0.0)
    total_dd = float(acct.get("total_drawdown_pct", 0.0) or 0.0)

    # ── FundedNext compliance check (gate before anything else) ──────
    # asdict() preserves ALL PropStatus fields (incl. new FN 2026 ones:
    # margin_used_pct, open_risk_pct, news_in_blackout, etc.) so the
    # dashboard + LLM brain always see the complete compliance snapshot.
    from dataclasses import asdict
    prop = await prop_rules.evaluate(state)
    prop_dump = asdict(prop)

    def _reject(reason: str) -> dict:
        assessment = RiskAssessment(
            approved=False, reason=reason,
            position_size_lots=0.0, stop_loss_pips=0, take_profit_pips=0,
            risk_reward_ratio=0.0,
            current_daily_drawdown_pct=daily_dd,
            current_total_drawdown_pct=total_dd,
        )
        return {**state, "risk": assessment.model_dump(), "prop_status": prop_dump}

    # Prop firm hard caps / internal targets reached
    if not prop.can_trade:
        return _reject(prop.block_reason or "Prop-firm guard active")

    if signal == "HOLD":
        return _reject("No actionable signal — standing aside")

    # ── Adaptive Policy Envelope checks ──────────────────────
    # 1. Session skip: uses a timestamp window (skip_session_until), NOT a
    #    boolean flag. Safe to call once per symbol — all symbols in this cycle
    #    will be rejected while now < skip_session_until (no "only first symbol
    #    gets skipped" bug from the original boolean-clear approach).
    skip, skip_reason = _ape.should_skip_session()
    if skip:
        return _reject(f"APE: session skipped — {skip_reason}")

    # 2. Symbol pause: brain paused this symbol after losses or bad conditions
    paused, pause_reason = _ape.is_symbol_paused(symbol)
    if paused:
        return _reject(f"APE: {symbol} paused — {pause_reason}")

    # 3. Conviction override: brain tightened the entry threshold
    conviction_override = _ape.get_conviction_override()
    effective_threshold = conviction_override if conviction_override else settings.min_conviction_threshold
    if strength < effective_threshold:
        return _reject(
            f"APE conviction gate: strength {strength:.2f} < threshold {effective_threshold:.2f}"
            + (f" (tightened by brain: {_ape.get_state().get('conviction_reason', '')})" if conviction_override else "")
        )

    # ── Economic calendar blackout ────────────────────────────
    if settings.economic_calendar_enabled:
        cal = state.get("economic_calendar") or {}
        if cal.get("in_blackout") and economic_calendar.symbol_affected(
            symbol, cal.get("affected_currencies", [])
        ):
            return _reject(f"Economic blackout: {cal.get('blackout_reason')} affects {symbol}")

    # ── Correlation guard ────────────────────────────────────
    if settings.correlation_guard_enabled:
        corr_state = state.get("correlation_report")
        if corr_state:
            from models.schemas import CorrelationReport
            report = CorrelationReport(**corr_state)
        else:
            report = correlation.build_report()
        blocked, reason = correlation.is_blocked(symbol, signal, report)
        if blocked:
            return _reject(f"Rejected: {reason}")

    # Minimum conviction threshold
    if strength < 0.55:
        return _reject(f"Signal conviction too low: {strength:.2f} < 0.55 threshold")

    # ── Concurrent positions cap ────────────────────────────────────
    existing = memory.retrieve("open_positions") or []
    if len(existing) >= settings.max_concurrent_positions:
        return _reject(
            f"Max concurrent positions reached: {len(existing)}/{settings.max_concurrent_positions}"
        )

    # ── Unified safe sizing — honors per-trade, daily, total, portfolio caps ──
    ind = state.get("indicators", {}).get(symbol, {})
    atr = ind.get("atr_14", 0.001) or 0.001
    vol_regimes = state.get("volatility_regimes", {}) if settings.volatility_regime_enabled else {}
    vol_mult = float((vol_regimes.get(symbol) or {}).get("size_multiplier", 1.0))
    current_open_risk = prop_rules.open_risk_pct(existing, starting)

    # APE risk multiplier: brain may have reduced sizing (0.3–1.0)
    ape_multiplier = _ape.get_risk_multiplier()

    sizing = compute_safe_sizing(
        symbol=symbol,
        strength=strength,
        atr=atr,
        equity=equity,
        starting_balance=starting,
        current_open_risk_pct=current_open_risk,
        prop_status=prop_dump,
        settings=settings,
        vol_mult=vol_mult,
        adaptive_risk_multiplier=ape_multiplier,
    )

    if sizing["rejected"]:
        return _reject(sizing.get("reject_reason") or f"Sizing blocked by {sizing['cap_reason']}")

    projected_open_risk = current_open_risk + sizing["risk_pct_of_starting"]

    ape_note = f" [APE risk×{ape_multiplier:.2f}]" if ape_multiplier < 1.0 else ""
    assessment = RiskAssessment(
        approved=True,
        reason=(
            f"Approved {sizing['lots']} lots on {symbol}{ape_note}: SL={sizing['sl_pips']}p "
            f"TP={sizing['tp_pips']}p (R/R={sizing['rr']}), risk=${sizing['risk_usd']:.2f} "
            f"({sizing['risk_pct_of_starting']:.2f}% of ${starting:,.0f} starting). "
            f"Bound by '{sizing['cap_reason']}' @ {sizing['budget_pct']:.2f}%. "
            f"Open risk now {projected_open_risk:.2f}%/{settings.max_total_open_risk_pct}%. "
            f"FN buffer: daily {prop.daily_buffer_pct:.2f}% (cap {prop.daily_loss_hard_cap_pct}%), "
            f"total {prop.total_buffer_pct:.2f}% (cap {prop.total_loss_hard_cap_pct}%)"
        ),
        position_size_lots=sizing["lots"],
        stop_loss_pips=sizing["sl_pips"],
        take_profit_pips=sizing["tp_pips"],
        risk_reward_ratio=sizing["rr"],
        current_daily_drawdown_pct=daily_dd,
        current_total_drawdown_pct=total_dd,
    )
    return {**state, "risk": assessment.model_dump(), "prop_status": prop_dump}
