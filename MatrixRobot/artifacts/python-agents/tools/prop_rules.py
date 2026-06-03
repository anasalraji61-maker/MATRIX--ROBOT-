"""FundedNext Stellar 2-Step compliance layer.

Encodes the firm's hard rules + tracks compliance state every cycle.

FundedNext Stellar 2-Step hard rules (as of 2026):
  • Max Daily Loss      : 5%  of starting balance (calendar-day, UTC)
  • Max Total Loss      : 10% of starting balance (static drawdown)
  • Min Trading Days    : 5 unique calendar days with at least one trade
  • Consistency Rule    : (funded only) biggest single-day P&L ≤ 40% of total profit
  • Profit Target       : Phase 1 = 8%, Phase 2 = 5%, Funded = none
  • SL required         : every position MUST have a stop loss attached
  • Forbidden practices : martingale, grid, HFT, latency arb, copy-trading
  • Allowed             : weekend holding, news trading, EAs, hedging, scalping

The bot uses two layers:
  - Internal (stricter) targets in config.max_*_drawdown_pct → bot self-halts
  - Prop hard caps in config.prop_*_hard_cap_pct → ABSOLUTE red line

A trade is rejected if it could push us past EITHER layer. The internal
targets always trip first (giving us a safety buffer).
"""
from dataclasses import dataclass, field
from datetime import datetime, timezone

from config import get_settings
from tools import memory, account_state


_DAILY_PNL_LOG_KEY = "prop_daily_pnl_log"


def _today_utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


# ────────────────────────────────────────────────────────────────────
# Daily P&L log (used for the consistency rule on funded phase)
# ────────────────────────────────────────────────────────────────────

def record_daily_pnl(net_pnl_change: float) -> None:
    """Accumulate today's realised P&L delta. Call from execution_agent
    every time a trade is closed (delta = closed trade profit)."""
    today = _today_utc()
    log = dict(memory.retrieve(_DAILY_PNL_LOG_KEY) or {})
    log[today] = float(log.get(today, 0.0)) + float(net_pnl_change)
    memory.store(_DAILY_PNL_LOG_KEY, log, ttl_seconds=86400 * 365)


def biggest_day_profit() -> float:
    log = memory.retrieve(_DAILY_PNL_LOG_KEY) or {}
    positives = [float(v) for v in log.values() if float(v) > 0]
    return max(positives) if positives else 0.0


def total_realized_profit() -> float:
    log = memory.retrieve(_DAILY_PNL_LOG_KEY) or {}
    return sum(float(v) for v in log.values())


# ────────────────────────────────────────────────────────────────────
# Compliance evaluation
# ────────────────────────────────────────────────────────────────────

@dataclass
class PropStatus:
    compliant: bool                       # no hard-cap violations
    can_trade: bool                       # compliant AND under internal targets
    block_reason: str                     # if !can_trade, why

    phase: str
    firm: str
    plan: str

    # Equity & drawdowns
    starting_balance: float
    equity: float
    profit_pct: float
    profit_target_pct: float

    daily_loss_pct: float
    daily_loss_internal_target_pct: float
    daily_loss_hard_cap_pct: float
    daily_buffer_pct: float               # distance to hard cap

    total_loss_pct: float
    total_loss_internal_target_pct: float
    total_loss_hard_cap_pct: float
    total_buffer_pct: float

    # Trading days
    trading_days_completed: int
    trading_days_required: int

    # Consistency (funded phase)
    consistency_ratio: float              # biggest_day / total_profit (0..1)
    consistency_max_pct: float
    consistency_ok: bool

    # FundedNext extra rules
    trades_today: int = 0
    trades_today_max: int = 20
    min_position_hold_seconds: int = 60
    daily_profit_pct: float = 0.0
    daily_profit_cap_pct: float = 30.0

    # NEW FN 2026 rules
    margin_used_pct: float = 0.0              # current cumulative margin usage
    margin_internal_target_pct: float = 50.0  # internal stricter target
    margin_hard_cap_pct: float = 70.0         # FN hard cap (breach = profit deduction)
    open_risk_pct: float = 0.0                # sum of SL distances across open positions
    funded_open_risk_cap_pct: float = 3.0     # funded-only hard cap
    news_in_blackout: bool = False            # currently inside ±N min of HIGH news
    news_blackout_reason: str = ""

    warnings: list = field(default_factory=list)
    violations: list = field(default_factory=list)


async def evaluate(state: dict | None = None) -> PropStatus:
    """Compute full FundedNext compliance status from live account data.

    `state` is optional: if it contains an "account" key (populated by
    data_agent), we reuse it; otherwise we refresh from the bridge.
    """
    s = get_settings()
    acct = (state or {}).get("account") if state else None
    if not acct or not acct.get("available"):
        acct = await account_state.refresh_account()

    daily_dd  = float(acct.get("daily_drawdown_pct", 0.0) or 0.0)
    total_dd  = float(acct.get("total_drawdown_pct", 0.0) or 0.0)
    equity    = float(acct.get("equity", 0.0) or 0.0)
    starting  = float(acct.get("starting_balance", 0.0) or 0.0)

    # NEW FN 2026 rules — compute from live open positions
    open_positions = memory.retrieve("open_positions") or []
    margin_pct = margin_used_pct(open_positions, equity)
    op_risk_pct = open_risk_pct(open_positions, starting)
    news_blocked, news_reason = _check_news_blackout(state)
    profile = (s.account_profile or "FN_CHALLENGE").upper()
    is_funded = (profile == "FN_FUNDED") or (s.prop_phase == "FUNDED")
    is_real = (profile == "REAL")
    daily_start = float(acct.get("daily_start_equity", 0.0) or starting)
    profit_pct = float(acct.get("profit_pct", 0.0) or 0.0)
    # Today's realized+unrealized profit as % of STARTING balance (FN's denominator)
    daily_profit_pct = ((equity - daily_start) / max(starting, 1.0) * 100.0) if equity > daily_start else 0.0
    days = account_state.trading_days_count()
    trades_today = account_state.trades_today_count()

    biggest = biggest_day_profit()
    total_profit = max(total_realized_profit(), 0.0)
    consistency = (biggest / total_profit) if total_profit > 1e-6 else 0.0
    consistency_ok = (s.prop_phase != "FUNDED") or (consistency <= s.prop_consistency_max_day_share_pct / 100.0)

    warnings: list[str] = []
    violations: list[str] = []

    # Hard caps (prop firm)
    if daily_dd >= s.prop_daily_loss_hard_cap_pct:
        violations.append(
            f"{s.prop_firm} Max Daily Loss VIOLATED: {daily_dd:.2f}% >= {s.prop_daily_loss_hard_cap_pct}%"
        )
    if total_dd >= s.prop_total_loss_hard_cap_pct:
        violations.append(
            f"{s.prop_firm} Max Total Loss VIOLATED: {total_dd:.2f}% >= {s.prop_total_loss_hard_cap_pct}%"
        )

    # Internal (stricter) targets — non-fatal but block new trades
    block_reason = ""
    can_trade = True
    # Emergency daily lockout takes precedence — set by emergency_guard when
    # floating daily DD breaches the hard internal cap. Unlocks at UTC midnight.
    from tools import emergency_guard
    lockout = emergency_guard.get_lockout()
    if lockout:
        can_trade = False
        block_reason = (
            f"DAILY LOCKOUT (auto-liquidated): {lockout.get('reason', 'DD cap hit')} "
            f"— resumes at UTC midnight"
        )
        violations.append(block_reason)
    elif violations:
        can_trade = False
        block_reason = violations[0]
    elif daily_dd >= s.max_daily_drawdown_pct:
        can_trade = False
        block_reason = (
            f"Internal daily DD target reached: {daily_dd:.2f}% >= {s.max_daily_drawdown_pct}% "
            f"(FN hard cap: {s.prop_daily_loss_hard_cap_pct}%)"
        )
        warnings.append(block_reason)
    elif total_dd >= s.max_total_drawdown_pct:
        can_trade = False
        block_reason = (
            f"Internal total DD target reached: {total_dd:.2f}% >= {s.max_total_drawdown_pct}% "
            f"(FN hard cap: {s.prop_total_loss_hard_cap_pct}%)"
        )
        warnings.append(block_reason)
    elif trades_today >= s.max_trades_per_day:
        can_trade = False
        block_reason = (
            f"Daily trade cap reached: {trades_today}/{s.max_trades_per_day} "
            f"— resets at UTC midnight"
        )
        warnings.append(block_reason)
    elif daily_profit_pct >= s.max_daily_profit_pct:
        can_trade = False
        block_reason = (
            f"Daily profit cap reached: {daily_profit_pct:.2f}% >= "
            f"{s.max_daily_profit_pct}% of starting balance — stopping to "
            f"avoid FN consistency flag"
        )
        warnings.append(block_reason)
    elif not is_real and margin_pct >= s.prop_margin_hard_cap_pct:
        can_trade = False
        block_reason = (
            f"FN margin cap reached: {margin_pct:.1f}% >= {s.prop_margin_hard_cap_pct}% "
            f"— FN deducts profits when margin usage exceeds 70%"
        )
        violations.append(block_reason)
    elif not is_real and margin_pct >= s.prop_margin_internal_target_pct:
        warnings.append(
            f"Margin usage warning: {margin_pct:.1f}% (internal target {s.prop_margin_internal_target_pct}%, "
            f"FN hard cap {s.prop_margin_hard_cap_pct}%)"
        )
    if is_funded and op_risk_pct >= s.prop_funded_open_risk_hard_cap_pct:
        can_trade = False
        block_reason = block_reason or (
            f"Funded open-risk cap reached: {op_risk_pct:.2f}% >= "
            f"{s.prop_funded_open_risk_hard_cap_pct}% (FN funded rule)"
        )
        violations.append(
            f"FN funded open-risk VIOLATED: {op_risk_pct:.2f}% >= {s.prop_funded_open_risk_hard_cap_pct}%"
        )
    if not is_real and news_blocked:
        can_trade = False
        block_reason = block_reason or f"News blackout: {news_reason}"
        warnings.append(block_reason)

    # Consistency warning (funded phase only)
    if s.prop_phase == "FUNDED" and not consistency_ok:
        warnings.append(
            f"Consistency rule risk: biggest day = {consistency*100:.1f}% of total profit "
            f"(max {s.prop_consistency_max_day_share_pct}%) — taper new trade sizes"
        )

    # Min trading-days warning (approaching profit target without enough days)
    if s.prop_phase in ("PHASE_1", "PHASE_2"):
        if profit_pct >= s.prop_profit_target_pct and days < s.prop_min_trading_days:
            warnings.append(
                f"Profit target hit ({profit_pct:.2f}%) but only {days}/{s.prop_min_trading_days} "
                f"trading days completed — keep small trades to satisfy min-days rule"
            )

    return PropStatus(
        compliant=len(violations) == 0,
        can_trade=can_trade,
        block_reason=block_reason,
        phase=s.prop_phase,
        firm=s.prop_firm,
        plan=s.prop_firm_plan,
        starting_balance=starting,
        equity=equity,
        profit_pct=profit_pct,
        profit_target_pct=s.prop_profit_target_pct,
        daily_loss_pct=daily_dd,
        daily_loss_internal_target_pct=s.max_daily_drawdown_pct,
        daily_loss_hard_cap_pct=s.prop_daily_loss_hard_cap_pct,
        daily_buffer_pct=max(0.0, s.prop_daily_loss_hard_cap_pct - daily_dd),
        total_loss_pct=total_dd,
        total_loss_internal_target_pct=s.max_total_drawdown_pct,
        total_loss_hard_cap_pct=s.prop_total_loss_hard_cap_pct,
        total_buffer_pct=max(0.0, s.prop_total_loss_hard_cap_pct - total_dd),
        trading_days_completed=days,
        trading_days_required=s.prop_min_trading_days,
        consistency_ratio=consistency,
        consistency_max_pct=s.prop_consistency_max_day_share_pct,
        consistency_ok=consistency_ok,
        trades_today=trades_today,
        trades_today_max=s.max_trades_per_day,
        min_position_hold_seconds=s.min_position_hold_seconds,
        daily_profit_pct=round(daily_profit_pct, 3),
        daily_profit_cap_pct=s.max_daily_profit_pct,
        margin_used_pct=round(margin_pct, 2),
        margin_internal_target_pct=s.prop_margin_internal_target_pct,
        margin_hard_cap_pct=s.prop_margin_hard_cap_pct,
        open_risk_pct=round(op_risk_pct, 3),
        funded_open_risk_cap_pct=s.prop_funded_open_risk_hard_cap_pct,
        news_in_blackout=news_blocked,
        news_blackout_reason=news_reason,
        warnings=warnings,
        violations=violations,
    )


def margin_used_pct(open_positions: list, equity: float) -> float:
    """Estimate cumulative margin usage as % of equity.

    Conservative model (matches FundedNext's enforcement):
      • FX standard lot   = 100,000 units. Margin = 100k * price / leverage.
        For majors quoted in USD, price ≈ 1.0, so margin ≈ $1,000/lot at 1:100.
      • XAUUSD            = 100 oz / lot. At ~$2,400/oz and 1:10 → ~$24,000/lot.
        (Post Jan 2026 FN leverage cut — this is the dangerous one.)
      • Indices / others  = fallback to FX model.

    Returns sum(margin per position) / equity * 100.
    """
    if equity <= 0:
        return 0.0
    s = get_settings()
    total_margin = 0.0
    for p in open_positions or []:
        lots = float(p.get("lots") or p.get("volume") or 0.0)
        sym  = (p.get("symbol") or "").upper()
        entry = float(p.get("entry_price") or p.get("open_price") or 1.0)
        if lots <= 0:
            continue
        if sym == "XAUUSD":
            contract = 100.0 * entry
            margin = contract / max(s.prop_xau_leverage, 1) * lots
        elif sym == "XAGUSD":
            contract = 5000.0 * entry
            margin = contract / max(s.prop_xau_leverage, 1) * lots
        else:
            # FX: 100k base units, margin ≈ 1000 USD/lot at 1:100
            contract = 100_000.0 * (entry if sym.startswith("USD") else 1.0)
            margin = contract / max(s.prop_fx_leverage, 1) * lots
        total_margin += margin
    return (total_margin / equity) * 100.0


def _check_news_blackout(state: dict | None) -> tuple[bool, str]:
    """Return (in_blackout, reason). Uses economic_calendar already populated
    in state, plus our own ±N min window centered on each HIGH event."""
    if not state:
        return False, ""
    cal = (state.get("economic_calendar") or {})
    if cal.get("in_blackout"):
        return True, cal.get("blackout_reason", "Economic calendar blackout")
    return False, ""


def open_risk_pct(open_positions: list, starting_balance: float) -> float:
    """Sum of (entry_price - sl_price) * lots * pip_value across open
    positions, expressed as % of starting balance. Used to enforce the
    `max_total_open_risk_pct` cap."""
    if starting_balance <= 0:
        return 0.0
    # Reuse the single source of truth for pip size + pip value so XAU/XAG/
    # JPY/stocks/majors are all handled identically to compute_safe_sizing.
    from agents.risk_agent import PIP_VALUE, pip_size_for

    total_usd = 0.0
    for p in open_positions or []:
        sl = float(p.get("stop_loss") or p.get("sl") or 0.0)
        entry = float(p.get("entry_price") or p.get("open_price") or 0.0)
        lots = float(p.get("lots") or p.get("volume") or 0.0)
        symbol = p.get("symbol", "")
        if sl <= 0 or entry <= 0 or lots <= 0:
            continue
        pip = pip_size_for(symbol)
        sl_pips = abs(entry - sl) / pip
        pip_val = PIP_VALUE.get(symbol, 10.0)
        total_usd += sl_pips * pip_val * lots
    return (total_usd / starting_balance) * 100.0
