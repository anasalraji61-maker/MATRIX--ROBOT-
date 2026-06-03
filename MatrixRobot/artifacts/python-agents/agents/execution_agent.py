"""
Execution Agent — final node in the LangGraph pipeline.

In PAPER_MODE: simulates fills and logs them.
In ACTIVE: sends real orders via the MT5 bridge.
In FROZEN: no-op.

Multi-position: opens trades for ALL analyses with strength >= min_conviction_threshold,
up to settings.max_concurrent_positions. Records each in state["executions"] list.
state["execution"] holds the primary (highest conviction) for dashboard compatibility.
"""
import logging
from config import get_settings
from models.schemas import ExecutionResult, CorrelationReport
from tools import mt5_bridge, memory, execution_variance, correlation, economic_calendar, prop_rules, accounts as accounts_mod, account_state
from tools.polygon import _mock_quotes
from agents.risk_agent import PIP_VALUE, compute_safe_sizing, pip_size_for

logger = logging.getLogger("matrix.execution")

_FALLBACK_EQUITY = 10_000.0


def _safe_sizing(symbol: str, strength: float, atr: float, settings,
                 equity: float, starting: float, current_open_risk_pct: float,
                 prop_status: dict | None, vol_mult: float = 1.0) -> dict:
    """Compute lots/SL/TP via the unified compute_safe_sizing helper.

    Applies execution variance to the FINAL output when enabled, so the
    core risk constraint math remains exact.
    """
    sizing = compute_safe_sizing(
        symbol=symbol, strength=strength, atr=atr,
        equity=equity, starting_balance=starting,
        current_open_risk_pct=current_open_risk_pct,
        prop_status=prop_status, settings=settings, vol_mult=vol_mult,
    )
    if sizing["rejected"]:
        return sizing
    if settings.exec_variance_enabled:
        j_lots = min(execution_variance.jitter_lots(sizing["lots"]), 5.0)
        j_sl   = execution_variance.jitter_pips(sizing["sl_pips"])
        j_tp   = execution_variance.jitter_pips(sizing["tp_pips"])
        budget = sizing["budget_usd"]
        pip_val = sizing["pip_val"]

        # Post-variance min-lot guard: if even 0.01 lots at the adjusted SL
        # exceed the budget, REJECT — we can't shrink below broker minimum
        # without breaking the cap.
        risk_at_min_after = j_sl * pip_val * 0.01
        if risk_at_min_after > budget and budget > 0:
            sizing["rejected"] = True
            sizing["reject_reason"] = (
                f"Post-variance min lot 0.01 at SL={j_sl}p would risk "
                f"${risk_at_min_after:.2f} > budget ${budget:.2f}"
            )
            sizing["lots"] = 0.0
            return sizing

        # Shrink adjusted lots if they exceed budget
        jittered_risk = j_sl * pip_val * j_lots
        if jittered_risk > budget and budget > 0:
            j_lots = max(0.01, round(budget / max(j_sl * pip_val, 1.0) - 0.005, 2))

        # Final guard: if even the shrunk version still exceeds budget
        # (rounding/floor edge case), HARD REJECT.
        final_risk = j_sl * pip_val * j_lots
        if final_risk > budget and budget > 0:
            sizing["rejected"] = True
            sizing["reject_reason"] = (
                f"Final risk ${final_risk:.2f} > budget ${budget:.2f} "
                f"after post-variance shrinkage (lots={j_lots}, SL={j_sl}p)"
            )
            sizing["lots"] = 0.0
            return sizing

        sizing["lots"]     = j_lots
        sizing["sl_pips"]  = j_sl
        sizing["tp_pips"]  = j_tp
        sizing["risk_usd"] = round(final_risk, 2)
    return sizing


async def _execute_one(symbol: str, action: str, sizing: dict, state: dict, settings, mode: str) -> ExecutionResult:
    """`sizing` is the pre-computed dict from _safe_sizing — caller has
    already verified `not sizing["rejected"]`."""
    quotes = state.get("market_data", {}).get("quotes", [])
    quote_map = {q["symbol"]: q for q in quotes}
    q = quote_map.get(symbol)
    if not q:
        mock = _mock_quotes([symbol])
        q = mock[0].model_dump() if mock else {"bid": 1.0, "ask": 1.0002, "mid": 1.0001}
    pip = sizing["pip"]

    if action == "BUY":
        entry = q["ask"]
        sl_price = round(entry - sizing["sl_pips"] * pip, 5)
        tp_price = round(entry + sizing["tp_pips"] * pip, 5)
    else:
        entry = q["bid"]
        sl_price = round(entry + sizing["sl_pips"] * pip, 5)
        tp_price = round(entry - sizing["tp_pips"] * pip, 5)

    # Apply entry timing window if execution variance is enabled
    if settings.exec_variance_enabled and mode == "ACTIVE":
        delay = await execution_variance.apply_entry_delay()
        if delay > 0:
            logger.info(f"[exec-variance] {symbol} {action} entry delayed {delay:.1f}s (fill window)")

    return await mt5_bridge.open_trade(
        symbol=symbol,
        action=action,
        lots=sizing["lots"],
        stop_loss_price=sl_price,
        take_profit_price=tp_price,
        mode=mode,
    )


async def run(state: dict) -> dict:
    settings = get_settings()
    mode = state.get("mode", settings.trading_state)
    risk = state.get("risk", {})

    # Build the raw candidate signal list ONCE — filtered only by conviction
    # threshold + valid action. This list is shared by primary AND every
    # secondary account so each runs independent existing-position / slot /
    # daily-cap filtering on its own state.
    analyses = state.get("analyses", [])
    raw_candidates = sorted(
        [a for a in analyses
         if a.get("signal") in ("BUY", "SELL")
         and a.get("strength", 0.0) >= settings.min_conviction_threshold],
        key=lambda a: a.get("strength", 0.0), reverse=True,
    )

    # ── PRIMARY PASS ───────────────────────────────────────────────────
    primary_dump, primary_executions = await _run_primary(
        state=state, settings=settings, mode=mode,
        raw_candidates=raw_candidates,
    )

    # ── SECONDARY FANOUT (always runs unless mode==FROZEN) ─────────────
    # Independent of primary outcome. Each secondary account has its own
    # bridge_url, equity, prop caps, position memory, and daily counter.
    secondary_executions: dict[str, list[dict]] = {}
    if mode != "FROZEN":
        try:
            secondaries = [a for a in accounts_mod.enabled_accounts() if a.id != "primary"]
            for acct in secondaries:
                try:
                    secondary_executions[acct.id] = await _run_for_account(
                        account=acct, raw_candidates=raw_candidates,
                        state=state, mode=mode, settings=settings,
                    )
                except Exception as e:
                    logger.exception(f"Secondary account {acct.id} fanout failed")
                    secondary_executions[acct.id] = [{
                        "executed": False, "mode": mode, "account": acct.id,
                        "message": f"Secondary account error: {e}",
                    }]
        except Exception as e:
            logger.warning(f"Multi-account fanout skipped: {e}")

    return {
        **state,
        "execution": primary_dump,
        "executions": primary_executions,
        "secondary_executions": secondary_executions,
    }


async def _run_primary(state: dict, settings, mode: str,
                       raw_candidates: list[dict]) -> tuple[dict, list[dict]]:
    """Primary-account execution pass.

    Returns (primary_dump, executions). Any early-skip path returns an
    empty executions list and a descriptive primary_dump — the secondary
    fanout still runs regardless.
    """
    # Mode = FROZEN: no trades at all.
    if mode == "FROZEN":
        return ExecutionResult(executed=False, mode=mode, message="Mode is FROZEN").model_dump(), []

    # Global drawdown limits + FundedNext compliance gate — pull live snapshot
    acct = state.get("account") or {}
    equity = float(acct.get("equity") or _FALLBACK_EQUITY)
    starting = float(acct.get("starting_balance") or equity or _FALLBACK_EQUITY)

    prop_dump = state.get("prop_status") or {}
    if prop_dump and not prop_dump.get("can_trade", True):
        return ExecutionResult(
            executed=False, mode=mode,
            message=f"Prop guard: {prop_dump.get('block_reason', 'compliance violation')}",
        ).model_dump(), []

    # NOTE: We deliberately do NOT short-circuit on `risk.approved == False`.
    # risk_agent evaluates only the single best_analysis; per-candidate guards
    # (correlation, calendar, conviction) below decide each remaining candidate.

    # Respect low-liquidity windows when execution variance is enabled
    if settings.exec_variance_enabled and mode == "ACTIVE":
        restricted, reason = execution_variance.is_low_liquidity_window()
        if restricted:
            logger.info(f"[exec-variance] Low-liquidity window ({reason}) — skipping execution this cycle")
            return ExecutionResult(
                executed=False, mode=mode,
                message=f"Low-liquidity window: {reason}",
            ).model_dump(), []

    # Existing positions — avoid duplicate symbol+direction
    existing = memory.retrieve("open_positions") or []
    existing_keys = {(p["symbol"], p["action"]) for p in existing}
    slots_left = max(0, settings.max_concurrent_positions - len(existing))

    if slots_left == 0:
        return ExecutionResult(
            executed=False, mode=mode,
            message=f"Max concurrent positions reached ({len(existing)}/{settings.max_concurrent_positions})",
        ).model_dump(), []

    # FundedNext daily trade cap — counted from UTC midnight, paper+live both
    from tools import account_state as _acct
    trades_today = _acct.trades_today_count()
    daily_room = max(0, settings.max_trades_per_day - trades_today)
    if daily_room == 0:
        return ExecutionResult(
            executed=False, mode=mode,
            message=f"Daily trade cap reached ({trades_today}/{settings.max_trades_per_day})",
        ).model_dump(), []
    slots_left = min(slots_left, daily_room)

    # Filter shared raw_candidates by primary's existing positions, then cap
    candidates = [
        a for a in raw_candidates
        if (a.get("symbol"), a.get("signal")) not in existing_keys
    ][:slots_left]

    if not candidates:
        return ExecutionResult(
            executed=False, mode=mode,
            message="No signals above conviction threshold",
        ).model_dump(), []

    # Per-cycle guards (build once, mutate as we open new positions)
    cal_state = state.get("economic_calendar") or {}
    cal_blackout = bool(cal_state.get("in_blackout"))
    cal_affected = cal_state.get("affected_currencies", [])
    corr_state = state.get("correlation_report")
    corr_report = CorrelationReport(**corr_state) if corr_state else correlation.build_report(existing)

    # Multi-execute
    executions: list[dict] = []
    primary = None
    for a in candidates:
        sym = a.get("symbol")
        act = a.get("signal")

        # Economic calendar blackout per-candidate
        if settings.economic_calendar_enabled and cal_blackout and \
                economic_calendar.symbol_affected(sym, cal_affected):
            executions.append({
                "executed": False, "mode": mode, "symbol": sym, "action": act,
                "message": f"calendar blackout: {cal_state.get('blackout_reason')}",
            })
            continue

        # Correlation guard per-candidate (use rolling report that includes
        # positions opened earlier *in this same cycle*)
        if settings.correlation_guard_enabled:
            blocked, reason = correlation.is_blocked(sym, act, corr_report)
            if blocked:
                executions.append({
                    "executed": False, "mode": mode, "symbol": sym, "action": act,
                    "message": reason,
                })
                continue

        # Low-conviction signal filter (only when execution variance enabled)
        if settings.exec_variance_enabled and execution_variance.should_skip_signal():
            logger.info(f"[exec-variance] Low-conviction filter applied on {sym} {act}")
            executions.append({
                "executed": False, "mode": mode, "symbol": sym,
                "action": act, "message": "exec-variance: low-conviction filter",
            })
            continue

        # Unified safe sizing — respects daily DD room, total DD room,
        # portfolio open-risk room, and per-trade cap simultaneously.
        ind = state.get("indicators", {}).get(sym, {})
        atr = ind.get("atr_14", 0.001) or 0.001
        vol_regimes = state.get("volatility_regimes", {}) if settings.volatility_regime_enabled else {}
        vol_mult = float((vol_regimes.get(sym) or {}).get("size_multiplier", 1.0))
        current_open_risk = prop_rules.open_risk_pct(existing, starting)

        sizing = _safe_sizing(
            symbol=sym, strength=a["strength"], atr=atr, settings=settings,
            equity=equity, starting=starting,
            current_open_risk_pct=current_open_risk,
            prop_status=prop_dump, vol_mult=vol_mult,
        )
        if sizing["rejected"]:
            executions.append({
                "executed": False, "mode": mode, "symbol": sym, "action": act,
                "message": sizing.get("reject_reason") or f"sizing blocked by {sizing['cap_reason']}",
            })
            continue

        # Mandatory SL — FundedNext requires every position to have a stop.
        # compute_safe_sizing always emits sl_pips>=15, but this is a defensive
        # final gate so a future bug can never send a naked order.
        if settings.require_stop_loss and sizing.get("sl_pips", 0) <= 0:
            executions.append({
                "executed": False, "mode": mode, "symbol": sym, "action": act,
                "message": "FN rule: stop-loss is mandatory — refusing naked order",
            })
            continue

        # Per-cycle daily trade cap re-check (in case earlier fills filled the day)
        if _acct.trades_today_count() >= settings.max_trades_per_day:
            executions.append({
                "executed": False, "mode": mode, "symbol": sym, "action": act,
                "message": f"Daily trade cap reached ({settings.max_trades_per_day})",
            })
            continue

        # ── Per-candidate FN compliance re-check ─────────────────────
        # `prop_status` from state was computed BEFORE this cycle's fills.
        # Re-evaluate every iteration so the margin 70% cap, funded 3%
        # open-risk cap, and news blackout can short-circuit mid-cycle.
        try:
            fresh_prop = await prop_rules.evaluate({**state, "account": acct})
            if not fresh_prop.can_trade:
                executions.append({
                    "executed": False, "mode": mode, "symbol": sym, "action": act,
                    "message": f"Prop guard re-check failed: {fresh_prop.block_reason}",
                })
                # Hard stop — no further candidates can fire either
                break
        except Exception as e:
            logger.warning(f"Per-candidate prop re-check failed for {sym}: {e}")

        try:
            res = await _execute_one(
                symbol=a["symbol"],
                action=a["signal"],
                sizing=sizing,
                state=state,
                settings=settings,
                mode=mode,
            )
            executions.append(res.model_dump())
            if res.executed:
                existing.append({
                    "trade_id": res.trade_id, "symbol": res.symbol, "action": res.action,
                    "lots": res.lots, "entry_price": res.entry_price,
                    "stop_loss": res.stop_loss, "take_profit": res.take_profit,
                    "mode": res.mode, "opened_at": res.timestamp, "pnl": 0.0,
                })
                # Daily trade counter — counted in BOTH paper and live so the
                # 20-trades/day cap applies uniformly (FN rule).
                _acct.record_trade_opened()
                # Mark today as a trading day for FundedNext min-days rule —
                # ONLY for real ACTIVE fills, never paper, so paper cycles can't
                # falsely satisfy the prop firm's min-5-days requirement.
                if mode == "ACTIVE":
                    _acct.record_trading_day()
                # Refresh correlation report so later candidates see this new exposure
                if settings.correlation_guard_enabled:
                    corr_report = correlation.build_report(existing)
                if primary is None:
                    primary = res
        except Exception as e:
            executions.append({
                "executed": False, "mode": mode, "symbol": a.get("symbol"),
                "action": a.get("signal"), "message": f"Execution error: {e}",
            })

    memory.store("open_positions", existing)

    if primary is None:
        primary_dump = ExecutionResult(
            executed=False, mode=mode,
            message=f"Attempted {len(candidates)} trades, none filled",
        ).model_dump()
    else:
        primary_dump = primary.model_dump()
        filled_count = sum(1 for e in executions if e.get("executed"))
        primary_dump["message"] = (
            f"{primary_dump.get('message','')} | Total filled this cycle: {filled_count}"
        )

    return primary_dump, executions


async def _run_for_account(account, raw_candidates: list, state: dict, mode: str, settings) -> list[dict]:
    """Mirror the primary execution pass onto a secondary MT5 account.

    Per-account: own bridge URL, own equity (refreshed live), own starting
    balance anchor, own risk-per-trade %, own daily-trades counter, own
    open-positions memory namespace. FN-style prop rules only enforced when
    `account.prop_firm` is set.
    """
    # Live equity for this account
    acct_snap = await account_state.refresh_account(
        account_id=account.id,
        bridge_url=account.bridge_url or None,
        starting_balance_override=account.starting_balance or None,
    )
    equity = float(acct_snap.get("equity") or 0.0)
    starting = float(acct_snap.get("starting_balance") or equity or 0.0)
    if equity <= 0 or starting <= 0:
        return [{
            "executed": False, "mode": mode, "account": account.id,
            "message": f"Account {account.id}: bridge offline or zero equity",
        }]

    # Shadow settings: secondaries use ONLY simple gates (DD + open-risk +
    # SL + slots + daily cap). Calendar / correlation are not applied —
    # those are FN-specific rules that don't belong on a real money account.
    class _AcctSettings:
        pass
    sset = _AcctSettings()
    for attr in (
        "sizing_safety_buffer_pct", "max_total_open_risk_pct",
        "require_stop_loss", "max_concurrent_positions",
        "max_trades_per_day", "min_conviction_threshold",
    ):
        setattr(sset, attr, getattr(settings, attr))
    sset.max_risk_per_trade_pct = float(account.risk_per_trade_pct)
    sset.max_daily_drawdown_pct = float(account.max_daily_drawdown_pct)
    sset.max_total_drawdown_pct = float(account.max_total_drawdown_pct)
    # Disabled for secondaries — keep their guards minimal
    sset.exec_variance_enabled = False
    sset.economic_calendar_enabled = False
    sset.correlation_guard_enabled = False
    sset.volatility_regime_enabled = False

    # Mimic prop_status for sizing (live DDs from the account snapshot)
    prop_dump = {
        "daily_loss_pct": float(acct_snap.get("daily_drawdown_pct") or 0.0),
        "total_loss_pct": float(acct_snap.get("total_drawdown_pct") or 0.0),
        "can_trade": True,
    }

    # Per-account open positions + daily trade counter
    pos_key = f"open_positions__{account.id}"
    existing = memory.retrieve(pos_key) or []
    existing_keys = {(p["symbol"], p["action"]) for p in existing}
    daily_room = max(0, sset.max_trades_per_day - account_state.trades_today_count(account.id))
    slots_left = max(0, sset.max_concurrent_positions - len(existing))
    slots_left = min(slots_left, daily_room)
    if slots_left == 0:
        return [{
            "executed": False, "mode": mode, "account": account.id,
            "message": f"No slots left ({len(existing)} open, {account_state.trades_today_count(account.id)}/{sset.max_trades_per_day} trades today)",
        }]

    quotes = state.get("market_data", {}).get("quotes", [])
    quote_map = {q["symbol"]: q for q in quotes}

    out: list[dict] = []
    filtered = [c for c in raw_candidates if (c.get("symbol"), c.get("signal")) not in existing_keys][:slots_left]
    for a in filtered:
        sym, act = a.get("symbol"), a.get("signal")

        ind = state.get("indicators", {}).get(sym, {})
        atr = ind.get("atr_14", 0.001) or 0.001
        vol_mult = 1.0
        current_open_risk = prop_rules.open_risk_pct(existing, starting)

        sizing = _safe_sizing(
            symbol=sym, strength=a["strength"], atr=atr, settings=sset,
            equity=equity, starting=starting,
            current_open_risk_pct=current_open_risk,
            prop_status=prop_dump, vol_mult=vol_mult,
        )
        if sizing["rejected"]:
            out.append({"executed": False, "account": account.id, "symbol": sym,
                        "action": act, "message": sizing.get("reject_reason") or sizing["cap_reason"]})
            continue

        # Build entry / SL / TP prices from the same quote feed
        q = quote_map.get(sym) or {"bid": 1.0, "ask": 1.0002}
        pip = sizing["pip"]
        if act == "BUY":
            entry = q["ask"]
            sl_price = round(entry - sizing["sl_pips"] * pip, 5)
            tp_price = round(entry + sizing["tp_pips"] * pip, 5)
        else:
            entry = q["bid"]
            sl_price = round(entry + sizing["sl_pips"] * pip, 5)
            tp_price = round(entry - sizing["tp_pips"] * pip, 5)

        try:
            res = await mt5_bridge.open_trade(
                symbol=sym, action=act, lots=sizing["lots"],
                stop_loss_price=sl_price, take_profit_price=tp_price,
                mode=mode, bridge_url=account.bridge_url or None,
            )
            entry_dump = res.model_dump()
            entry_dump["account"] = account.id
            out.append(entry_dump)
            if res.executed:
                existing.append({
                    "trade_id": res.trade_id, "symbol": res.symbol, "action": res.action,
                    "lots": res.lots, "entry_price": res.entry_price,
                    "stop_loss": res.stop_loss, "take_profit": res.take_profit,
                    "mode": res.mode, "opened_at": res.timestamp, "pnl": 0.0,
                    "account": account.id,
                })
                account_state.record_trade_opened(account.id)
                if mode == "ACTIVE":
                    account_state.record_trading_day(account.id)
        except Exception as e:
            out.append({"executed": False, "account": account.id, "symbol": sym,
                        "action": act, "message": f"Execution error: {e}"})

    memory.store(pos_key, existing)
    return out
