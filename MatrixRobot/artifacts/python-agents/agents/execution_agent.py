"""
Execution Agent — final node in the LangGraph pipeline.

In PAPER_MODE: simulates fills and logs them.
In ACTIVE: sends real orders via the MT5 bridge.
In FROZEN: no-op.

Multi-position: opens trades ONLY from Supervisor `decision.approved_trades`
(up to open slots / daily cap). Records each in state["executions"] list.
state["execution"] holds the primary (highest conviction) for dashboard compatibility.
"""
import logging
from config import get_settings
from models.schemas import ExecutionResult, CorrelationReport
from tools import mt5_bridge, memory, correlation, economic_calendar, prop_rules, accounts as accounts_mod, account_state
from tools.polygon import _mock_quotes
from agents.risk_agent import compute_safe_sizing
from tools import trade_tiers, position_reconciler

logger = logging.getLogger("matrix.execution")

_FALLBACK_EQUITY = 10_000.0


def _batch_halted_after_execute(mode: str, res: ExecutionResult) -> bool:
    """Stop same-cycle batch when manual check is active (P0)."""
    if mode != "ACTIVE":
        return False
    if getattr(res, "manual_check_required", False):
        return True
    from tools.bridge_manual import is_blocking
    return is_blocking()


def _supervisor_candidates(state: dict, settings) -> list[dict]:
    """Execution follows Supervisor approved_trades only (Phase 1.1)."""
    decision = state.get("decision") or {}
    approved = decision.get("approved_trades") or []
    if not approved:
        return []

    min_strength = trade_tiers.min_candidate_strength(settings)
    candidates: list[dict] = []
    for item in approved:
        signal = str(item.get("signal", "")).upper()
        symbol = str(item.get("symbol", "")).strip()
        strength = float(item.get("strength") or 0.0)
        if signal not in ("BUY", "SELL") or not symbol:
            continue
        if strength < min_strength:
            continue
        candidates.append({
            "symbol": symbol,
            "signal": signal,
            "strength": strength,
        })

    return sorted(candidates, key=lambda a: a.get("strength", 0.0), reverse=True)


def _sizing_for_candidate(state: dict, symbol: str, action: str) -> dict | None:
    for t in state.get("approved_risk_trades") or []:
        if t.get("symbol") == symbol and str(t.get("signal", "")).upper() == action.upper():
            return t.get("sizing")
    return None


async def _execute_one(symbol: str, action: str, sizing: dict, state: dict, settings, mode: str) -> ExecutionResult:
    quotes = state.get("market_data", {}).get("quotes", [])
    quote_map = {q["symbol"]: q for q in quotes}
    q = quote_map.get(symbol)
    if not q:
        if mode == "ACTIVE":
            return ExecutionResult(
                executed=False, mode=mode, symbol=symbol, action=action,
                message="No live quote — mock data blocked in ACTIVE",
            )
        from tools.polygon import _mock_quotes
        mock = _mock_quotes([symbol])
        q = mock[0].model_dump() if mock else None
    if not q:
        return ExecutionResult(
            executed=False, mode=mode, symbol=symbol, action=action,
            message="No quote available for execution",
        )
    pip = sizing["pip"]

    if action == "BUY":
        entry = q["ask"]
        sl_price = round(entry - sizing["sl_pips"] * pip, 5)
        tp_price = round(entry + sizing["tp_pips"] * pip, 5)
    else:
        entry = q["bid"]
        sl_price = round(entry + sizing["sl_pips"] * pip, 5)
        tp_price = round(entry - sizing["tp_pips"] * pip, 5)

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

    if mode == "ACTIVE":
        from tools.bridge_manual import is_blocking
        if is_blocking():
            msg = "Unresolved MT5 position ticket — manual check required; execution blocked"
            return {
                **state,
                "execution": ExecutionResult(executed=False, mode=mode, message=msg).model_dump(),
                "executions": [],
                "secondary_executions": {},
            }

    # Supervisor-approved batch only — shared by primary and secondary accounts.
    raw_candidates = _supervisor_candidates(state, settings)
    if not raw_candidates:
        logger.info("No supervisor-approved trades — execution skipped")

    # ── PRIMARY PASS ───────────────────────────────────────────────────
    primary_dump, primary_executions = await _run_primary(
        state=state, settings=settings, mode=mode,
        raw_candidates=raw_candidates,
    )

    # ── SECONDARY FANOUT (disabled in ACTIVE unless explicitly enabled) ──
    secondary_executions: dict[str, list[dict]] = {}
    allow_secondary = mode != "FROZEN" and (
        mode != "ACTIVE" or getattr(settings, "active_secondary_fanout", False)
    )
    if allow_secondary:
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
    if mode == "FROZEN":
        return ExecutionResult(executed=False, mode=mode, message="Mode is FROZEN").model_dump(), []

    if mode == "ACTIVE":
        bridge_ok = await position_reconciler.ensure_synced()
        if not bridge_ok:
            return ExecutionResult(
                executed=False, mode=mode,
                message="MT5 state unknown — bridge unreachable, execution blocked",
            ).model_dump(), []

    acct = state.get("account") or {}
    equity = float(acct.get("equity") or _FALLBACK_EQUITY)
    starting = float(acct.get("starting_balance") or equity or _FALLBACK_EQUITY)

    prop_dump = state.get("prop_status") or {}
    if prop_dump and not prop_dump.get("can_trade", True):
        return ExecutionResult(
            executed=False, mode=mode,
            message=f"Prop guard: {prop_dump.get('block_reason', 'compliance violation')}",
        ).model_dump(), []

    # Count slots from live MT5 (not stale memory) so we never exceed max concurrent.
    bridge_url = (settings.mt5_bridge_url or "").rstrip("/") or None
    if mode == "ACTIVE" and bridge_url:
        existing = await account_state.sync_open_positions(bridge_url=bridge_url) or []
    else:
        existing = memory.retrieve("open_positions") or []
    existing_keys = {(p["symbol"], p["action"]) for p in existing}
    open_count = len(existing)
    slots_left = max(0, settings.max_concurrent_positions - open_count)

    if slots_left == 0:
        return ExecutionResult(
            executed=False, mode=mode,
            message=f"Max concurrent positions reached ({open_count}/{settings.max_concurrent_positions})",
        ).model_dump(), []

    from tools import account_state as _acct
    trades_today = _acct.trades_today_count()
    daily_room = max(0, settings.max_trades_per_day - trades_today)
    if daily_room == 0:
        return ExecutionResult(
            executed=False, mode=mode,
            message=f"Daily trade cap reached ({trades_today}/{settings.max_trades_per_day})",
        ).model_dump(), []
    slots_left = min(slots_left, daily_room)

    candidates = [
        a for a in raw_candidates
        if (a.get("symbol"), a.get("signal")) not in existing_keys
    ][:slots_left]

    if not candidates:
        return ExecutionResult(
            executed=False, mode=mode,
            message="No supervisor-approved trades to execute",
        ).model_dump(), []

    cal_state = state.get("economic_calendar") or {}
    cal_affected = cal_state.get("affected_currencies", [])
    profile = getattr(settings, "account_profile", "FN_CHALLENGE")
    is_funded = profile.upper() == "FN_FUNDED"
    corr_state = state.get("correlation_report")
    corr_report = CorrelationReport(**corr_state) if corr_state else correlation.build_report(existing)

    executions: list[dict] = []
    primary = None
    for a in candidates:
        sym = a.get("symbol")
        act = a.get("signal")

        try:
            from tools import self_learning
            blocked, why = self_learning.is_blocked(sym, act)
            if blocked:
                executions.append({
                    "executed": False, "mode": mode, "symbol": sym, "action": act,
                    "message": f"Self-learning block: {why}",
                })
                continue
        except Exception:
            pass

        news_blocked, news_reason = prop_rules.check_news_blackout(
            state, settings, profile, is_funded,
        )
        if settings.economic_calendar_enabled and news_blocked and \
                economic_calendar.symbol_affected(sym, cal_affected):
            executions.append({
                "executed": False, "mode": mode, "symbol": sym, "action": act,
                "message": f"News policy: {news_reason}",
            })
            continue

        if settings.correlation_guard_enabled:
            blocked, reason = correlation.is_blocked(sym, act, corr_report)
            if blocked:
                executions.append({
                    "executed": False, "mode": mode, "symbol": sym, "action": act,
                    "message": reason,
                })
                continue

        tier = trade_tiers.classify_trade_tier(a.get("strength", 0.0), settings)
        if tier == "HOLD":
            executions.append({
                "executed": False, "mode": mode, "symbol": sym, "action": act,
                "message": f"Below trade tier minimum ({settings.small_trade_min_strength})",
            })
            continue
        if tier == "SMALL":
            if account_state.count_small_open_positions(existing) >= settings.small_trade_max_open:
                executions.append({
                    "executed": False, "mode": mode, "symbol": sym, "action": act,
                    "message": f"Small-trade open cap ({settings.small_trade_max_open})",
                })
                continue
            if account_state.small_trades_today_count() >= settings.small_trade_max_per_day:
                executions.append({
                    "executed": False, "mode": mode, "symbol": sym, "action": act,
                    "message": f"Small-trade daily cap ({settings.small_trade_max_per_day}/day)",
                })
                continue

        ind = state.get("indicators", {}).get(sym, {})
        atr = ind.get("atr_14", 0.001) or 0.001
        vol_regimes = state.get("volatility_regimes", {}) if settings.volatility_regime_enabled else {}
        vol_mult = float((vol_regimes.get(sym) or {}).get("size_multiplier", 1.0))
        current_open_risk = prop_rules.open_risk_pct(existing, starting)
        session = state.get("session_profile") or {}
        quote_map = {q["symbol"]: q for q in (state.get("market_data") or {}).get("quotes", [])}

        from tools.data_quality import symbol_quarantine_reason
        from tools.session_engine import check_symbol_session_allowed

        dq_reason = symbol_quarantine_reason(sym, state, mode)
        if dq_reason:
            executions.append({
                "executed": False, "mode": mode, "symbol": sym, "action": act,
                "message": f"Data quarantine: {dq_reason}",
            })
            continue

        sess_ok, sess_reason, _shadow = check_symbol_session_allowed(
            sym, tier, session, settings,
        )
        if not sess_ok:
            executions.append({
                "executed": False, "mode": mode, "symbol": sym, "action": act,
                "message": f"Session filter: {sess_reason}",
            })
            continue

        from tools.liquidity_guard import check_spread
        spread_ok, spread_reason = check_spread(sym, quote_map.get(sym), settings)
        if not spread_ok:
            executions.append({
                "executed": False, "mode": mode, "symbol": sym, "action": act,
                "message": f"Liquidity guard: {spread_reason}",
            })
            continue

        sizing = _sizing_for_candidate(state, sym, act)
        if not sizing:
            sizing = compute_safe_sizing(
                symbol=sym, strength=a["strength"], atr=atr, settings=settings,
                equity=equity, starting_balance=starting,
                current_open_risk_pct=current_open_risk,
                prop_status=prop_dump, vol_mult=vol_mult,
                max_risk_pct_override=trade_tiers.risk_pct_for_tier(tier, settings),
                trade_tier=tier,
                session_profile=session,
            )
        if sizing["rejected"]:
            executions.append({
                "executed": False, "mode": mode, "symbol": sym, "action": act,
                "message": sizing.get("reject_reason") or f"sizing blocked by {sizing['cap_reason']}",
            })
            continue

        min_rr = trade_tiers.rr_minimum_for_tier(tier, settings)
        if float(sizing.get("rr") or 0) < min_rr:
            executions.append({
                "executed": False, "mode": mode, "symbol": sym, "action": act,
                "message": f"{tier} trade R/R {sizing.get('rr')} < {min_rr}",
            })
            continue

        from tools.surgical_filters import check_entry_gates
        gate_ok, gate_reason = check_entry_gates(
            sym, float(a.get("strength") or 0), float(sizing.get("rr") or 0),
            settings=settings, trade_tier=tier,
        )
        if not gate_ok:
            executions.append({
                "executed": False, "mode": mode, "symbol": sym, "action": act,
                "message": gate_reason,
            })
            continue

        if settings.require_stop_loss and sizing.get("sl_pips", 0) <= 0:
            executions.append({
                "executed": False, "mode": mode, "symbol": sym, "action": act,
                "message": "FN rule: stop-loss is mandatory — refusing naked order",
            })
            continue

        if _acct.trades_today_count() >= settings.max_trades_per_day:
            executions.append({
                "executed": False, "mode": mode, "symbol": sym, "action": act,
                "message": f"Daily trade cap reached ({settings.max_trades_per_day})",
            })
            continue

        try:
            fresh_prop = await prop_rules.evaluate({**state, "account": acct})
            if not fresh_prop.can_trade:
                executions.append({
                    "executed": False, "mode": mode, "symbol": sym, "action": act,
                    "message": f"Prop guard re-check failed: {fresh_prop.block_reason}",
                })
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
            if _batch_halted_after_execute(mode, res):
                executions.append({
                    "executed": False,
                    "mode": mode,
                    "message": "Batch halted — unresolved MT5 position ticket requires manual check",
                })
                break
            if res.executed:
                quote = quote_map.get(sym) or {}
                spread_pips = quote.get("spread_pips") or quote.get("spread")
                council = a.get("council") or {}
                brains = council.get("brains") or []
                skeptic = next((b for b in brains if b.get("brain") == "skeptic"), {})
                risk_br = next((b for b in brains if b.get("brain") == "risk_prop"), {})
                existing.append({
                    "trade_id": res.trade_id, "symbol": res.symbol, "action": res.action,
                    "lots": res.lots, "entry_price": res.entry_price,
                    "stop_loss": res.stop_loss, "take_profit": res.take_profit,
                    "initial_stop_loss": res.stop_loss,
                    "mode": res.mode, "opened_at": res.timestamp, "pnl": 0.0,
                    "trade_tier": tier,
                    "strategy": a.get("strategy") or a.get("strategy_name"),
                    "strategy_name": a.get("strategy") or a.get("strategy_name"),
                    "strength": float(a.get("strength") or 0),
                    "spread_at_entry": spread_pips,
                    "spread_pips": spread_pips,
                    "council_approved": council.get("approved"),
                    "council_meta_score": council.get("meta_score"),
                    "skeptic_vote": skeptic.get("vote") or skeptic.get("short_reason"),
                    "risk_vote": risk_br.get("vote") or risk_br.get("short_reason"),
                    "entry_reason": a.get("entry_reason") or a.get("reason", ""),
                })
                _acct.record_trade_opened()
                if tier == "SMALL":
                    _acct.record_small_trade_opened()
                try:
                    from tools.off_session_limits import is_off_session, record_trade_opened as _off_open
                    if is_off_session(state.get("session_profile") or {}, settings):
                        _off_open()
                except Exception:
                    pass
                if mode == "ACTIVE":
                    _acct.record_trading_day()
                if settings.correlation_guard_enabled:
                    corr_report = correlation.build_report(existing)
                if primary is None:
                    primary = res
            else:
                try:
                    from tools import self_learning
                    self_learning.record_event(
                        layer="execution",
                        kind="execution_fail",
                        symbol=sym,
                        side=act,
                        reason=res.message or "not executed",
                        severity="high",
                    )
                except Exception:
                    pass
        except Exception as e:
            executions.append({
                "executed": False, "mode": mode, "symbol": a.get("symbol"),
                "action": a.get("signal"), "message": f"Execution error: {e}",
            })
            try:
                from tools import self_learning
                self_learning.record_event(
                    layer="execution",
                    kind="execution_fail",
                    symbol=a.get("symbol"),
                    side=a.get("signal"),
                    reason=str(e),
                    severity="high",
                )
            except Exception:
                pass

    memory.store("open_positions", existing)

    if mode == "ACTIVE":
        await position_reconciler.ensure_synced()

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


def _account_settings(account, settings):
    """Build a settings-like object with per-account overrides."""
    class _AcctSettings:
        pass

    sset = _AcctSettings()
    for attr in (
        "sizing_safety_buffer_pct", "max_total_open_risk_pct",
        "require_stop_loss",
        "real_micro_equity_threshold", "real_micro_max_risk_per_trade_pct",
        "real_micro_strength_floor_for_sizing",
        "enable_small_trades", "small_trade_min_strength",
        "normal_trade_min_strength", "small_trade_max_risk_pct",
        "small_trade_max_per_day", "small_trade_max_open",
        "small_trade_require_rr_min", "normal_trade_require_rr_min",
    ):
        setattr(sset, attr, getattr(settings, attr))
    sset.max_risk_per_trade_pct = float(account.risk_per_trade_pct)
    sset.max_daily_drawdown_pct = float(account.max_daily_drawdown_pct)
    sset.max_total_drawdown_pct = float(account.max_total_drawdown_pct)
    profile = str(account.account_profile or settings.account_profile).upper()
    sset.max_concurrent_positions = int(
        account.max_concurrent_positions
        or (settings.real_max_concurrent_positions if profile == "REAL" else settings.max_concurrent_positions)
    )
    sset.max_trades_per_day = int(
        account.max_trades_per_day
        or (settings.real_max_trades_per_day if profile == "REAL" else settings.max_trades_per_day)
    )
    sset.min_conviction_threshold = float(
        account.min_conviction_threshold or settings.min_conviction_threshold
    )
    sset.account_profile = str(account.account_profile or settings.account_profile).upper()
    sset.economic_calendar_enabled = False
    sset.correlation_guard_enabled = False
    sset.volatility_regime_enabled = False
    return sset


async def _run_for_account(account, raw_candidates: list, state: dict, mode: str, settings) -> list[dict]:
    pos_key = "open_positions" if account.id == "primary" else f"open_positions__{account.id}"
    bridge_url = (account.bridge_url or "").rstrip("/") or None
    acct_id = account.id if account.id != "primary" else None
    if mode == "ACTIVE" and bridge_url:
        existing = await account_state.sync_open_positions(
            account_id=acct_id, bridge_url=bridge_url,
        ) or []
    else:
        existing = memory.retrieve(pos_key) or []

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

    sset = _account_settings(account, settings)
    min_conv = sset.min_conviction_threshold

    prop_dump = {
        "daily_loss_pct": float(acct_snap.get("daily_drawdown_pct") or 0.0),
        "total_loss_pct": float(acct_snap.get("total_drawdown_pct") or 0.0),
        "can_trade": True,
    }

    existing_keys = {(p["symbol"], p["action"]) for p in existing}
    open_count = len(existing)
    daily_room = max(0, sset.max_trades_per_day - account_state.trades_today_count(account.id))
    slots_left = max(0, sset.max_concurrent_positions - open_count)
    slots_left = min(slots_left, daily_room)
    if slots_left == 0:
        return [{
            "executed": False, "mode": mode, "account": account.id,
            "message": f"No slots left ({open_count} open, {account_state.trades_today_count(account.id)}/{sset.max_trades_per_day} trades today)",
        }]

    quotes = state.get("market_data", {}).get("quotes", [])
    quote_map = {q["symbol"]: q for q in quotes}

    out: list[dict] = []
    filtered = [
        c for c in raw_candidates
        if (c.get("symbol"), c.get("signal")) not in existing_keys
        and c.get("strength", 0.0) >= min_conv
        and account.allows_symbol(c.get("symbol", ""))
    ][:slots_left]
    for a in filtered:
        sym, act = a.get("symbol"), a.get("signal")

        ind = state.get("indicators", {}).get(sym, {})
        atr = ind.get("atr_14", 0.001) or 0.001
        current_open_risk = prop_rules.open_risk_pct(existing, starting)

        sizing = compute_safe_sizing(
            symbol=sym, strength=a["strength"], atr=atr, settings=sset,
            equity=equity, starting_balance=starting,
            current_open_risk_pct=current_open_risk,
            prop_status=prop_dump, vol_mult=1.0,
        )
        if sizing["rejected"]:
            out.append({"executed": False, "account": account.id, "symbol": sym,
                        "action": act, "message": sizing.get("reject_reason") or sizing["cap_reason"]})
            continue

        q = quote_map.get(sym)
        if not q:
            out.append({
                "executed": False, "account": account.id, "symbol": sym,
                "action": act, "message": "No live quote — mock data blocked in ACTIVE",
            })
            continue
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
            if _batch_halted_after_execute(mode, res):
                out.append({
                    "executed": False, "mode": mode, "account": account.id,
                    "message": "Batch halted — unresolved MT5 position ticket requires manual check",
                })
                break
            if res.executed:
                existing.append({
                    "trade_id": res.trade_id, "symbol": res.symbol, "action": res.action,
                    "lots": res.lots, "entry_price": res.entry_price,
                    "stop_loss": res.stop_loss, "take_profit": res.take_profit,
                    "initial_stop_loss": res.stop_loss,
                    "mode": res.mode, "opened_at": res.timestamp, "pnl": 0.0,
                    "account": account.id,
                })
                account_state.record_trade_opened(account.id)
                if mode == "ACTIVE":
                    account_state.record_trading_day(account.id)
                try:
                    from tools import telegram_alerts
                    if get_settings().has_telegram:
                        await telegram_alerts.alert_trade(
                            account.id, res.symbol, res.action, res.lots,
                            res.entry_price, res.stop_loss, res.take_profit,
                        )
                except Exception:
                    pass
        except Exception as e:
            out.append({"executed": False, "account": account.id, "symbol": sym,
                        "action": act, "message": f"Execution error: {e}"})

    memory.store(pos_key, existing)
    return out
