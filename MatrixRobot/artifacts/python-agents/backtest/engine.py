"""
Deterministic backtest engine for the Matrix Robot strategy stack.

Why deterministic (no LLM brain in the loop)?
  - Calling Claude on every historical bar would cost hundreds of dollars
    and take days for 6 months of H1 data.
  - A backtest answers "does our STRATEGY logic have edge?" — the LLM brain
    is a router/selector on top of the same tools, so testing the tools
    deterministically lower-bounds the system's edge.
  - Reproducibility: same bars in → same trades out, every run.

Pipeline per bar t:
  window = bars[:t+1]                  (only past + current, no look-ahead)
  ind    = compute_indicators(symbol, window)
  ict    = ict_smc.analyze(symbol, window)
  signal = simple_score(ind, ict)      (mirrors analysis_agent rule path)
  if flat and signal in (BUY, SELL):
      open trade @ close[t] with SL = 1.5×ATR, TP = 2×SL
  else if open:
      check SL/TP hit on bars[t+1] OHLC; close if hit OR after MAX_BARS_HELD

Output: per-trade list + aggregate stats (win_rate, profit_factor, R-multiple
total, max DD, Sharpe-ish).
"""
from __future__ import annotations
import logging
import math
from dataclasses import dataclass, asdict, field
from typing import Optional

from tools import twelve_data
from tools import indicators as _ind
from tools import ict_smc as _ict

logger = logging.getLogger("matrix.backtest")

# Mirror the live ensemble weights (subset — MTF/sentiment skipped, see notes).
_W = {
    "rsi": 1.0, "stoch": 0.6, "macd": 0.9, "ema_stack": 1.0,
    "ema200": 0.7, "adx": 0.8, "ichimoku": 0.6,
}
_ICT_W = 3.5  # ICT/SMC weight (matches live default)

MIN_WARMUP_BARS = 220      # need ≥200 for EMA200, +buffer for ICT swings
MAX_BARS_HELD = 48         # close stale trades after ~2 days of H1 bars
SIGNAL_THRESHOLD = 0.25    # |normalised score| ≥ this triggers a trade
SL_ATR_MULT = 1.5
TP_RR = 2.0                # TP at 2R


@dataclass
class Trade:
    symbol: str
    side: str               # "BUY" | "SELL"
    entry_idx: int
    entry_price: float
    exit_idx: Optional[int] = None
    exit_price: Optional[float] = None
    sl: float = 0.0
    tp: float = 0.0
    bars_held: int = 0
    pnl_r: float = 0.0      # R-multiple (loss = -1, win = +TP_RR)
    exit_reason: str = ""   # "SL" | "TP" | "TIMEOUT" | "EOD"


@dataclass
class BacktestResult:
    symbol: str
    timeframe: str
    bars_count: int
    warmup_bars: int
    trades: list[dict] = field(default_factory=list)
    stats: dict = field(default_factory=dict)


def _score_bar(ind: dict, ict: dict) -> float:
    """Reduced ensemble score in [-1, +1]. Mirrors analysis_agent rules."""
    score = 0.0

    def push(weight: float, cond: bool, sign: int):
        nonlocal score
        if cond:
            score += sign * weight

    rsi = ind.get("rsi_14")
    if rsi is not None:
        push(_W["rsi"], rsi < 35, +1)
        push(_W["rsi"], rsi > 65, -1)

    sk = ind.get("stoch_k")
    if sk is not None:
        push(_W["stoch"], sk < 20, +1)
        push(_W["stoch"], sk > 80, -1)

    mh = ind.get("macd_hist")
    if mh is not None:
        push(_W["macd"], mh > 0, +1)
        push(_W["macd"], mh < 0, -1)

    e20, e50, e200 = ind.get("ema_20"), ind.get("ema_50"), ind.get("ema_200")
    if e20 and e50:
        push(_W["ema_stack"], e20 > e50, +1)
        push(_W["ema_stack"], e20 < e50, -1)
    mid = ind.get("bb_mid")
    if e200 and mid:
        push(_W["ema200"], mid > e200, +1)
        push(_W["ema200"], mid < e200, -1)

    adx = ind.get("adx_14")
    dip, dim = ind.get("di_plus"), ind.get("di_minus")
    if adx is not None and adx >= 25 and dip is not None and dim is not None:
        push(_W["adx"], dip > dim, +1)
        push(_W["adx"], dim > dip, -1)

    ich = ind.get("ichimoku_above_cloud")
    if ich is True:  score += _W["ichimoku"]
    if ich is False: score -= _W["ichimoku"]

    ict_score = float((ict or {}).get("score", 0.0) or 0.0)
    if abs(ict_score) >= 0.20:
        score += _ICT_W * ict_score

    max_score = sum(_W.values()) + _ICT_W
    return max(-1.0, min(1.0, score / max_score))


def _open_trade(symbol: str, side: str, idx: int, price: float, atr: float) -> Trade:
    sl_dist = max(atr * SL_ATR_MULT, price * 0.0005)  # min 5 pips equiv
    if side == "BUY":
        sl = price - sl_dist
        tp = price + sl_dist * TP_RR
    else:
        sl = price + sl_dist
        tp = price - sl_dist * TP_RR
    return Trade(symbol=symbol, side=side, entry_idx=idx,
                 entry_price=price, sl=sl, tp=tp)


def _check_exit(trade: Trade, bar: dict, idx: int) -> bool:
    """Update trade in-place if SL/TP hit on this bar. Conservative tie-break:
    if both SL and TP are inside the bar's range, assume SL hit first
    (worst case). Returns True if trade closed."""
    high, low = bar["high"], bar["low"]
    hit_sl = (low <= trade.sl) if trade.side == "BUY" else (high >= trade.sl)
    hit_tp = (high >= trade.tp) if trade.side == "BUY" else (low <= trade.tp)
    if hit_sl and hit_tp:
        trade.exit_price = trade.sl
        trade.exit_reason = "SL"
        trade.pnl_r = -1.0
    elif hit_sl:
        trade.exit_price = trade.sl
        trade.exit_reason = "SL"
        trade.pnl_r = -1.0
    elif hit_tp:
        trade.exit_price = trade.tp
        trade.exit_reason = "TP"
        trade.pnl_r = TP_RR
    else:
        return False
    trade.exit_idx = idx
    trade.bars_held = idx - trade.entry_idx
    return True


def _stats(trades: list[Trade], n_bars: int) -> dict:
    if not trades:
        return {"n_trades": 0, "win_rate": 0.0, "total_r": 0.0,
                "avg_r": 0.0, "profit_factor": 0.0, "max_dd_r": 0.0,
                "sharpe_like": 0.0, "trades_per_100_bars": 0.0,
                "exposure_pct": 0.0}
    rs = [t.pnl_r for t in trades]
    wins = [r for r in rs if r > 0]
    losses = [r for r in rs if r < 0]
    gross_win = sum(wins)
    gross_loss = -sum(losses)
    pf = (gross_win / gross_loss) if gross_loss > 0 else (math.inf if gross_win > 0 else 0.0)
    # equity curve in R
    eq = 0.0; peak = 0.0; max_dd = 0.0
    for r in rs:
        eq += r
        peak = max(peak, eq)
        max_dd = min(max_dd, eq - peak)
    mean = sum(rs) / len(rs)
    var = sum((r - mean) ** 2 for r in rs) / len(rs)
    std = math.sqrt(var) if var > 0 else 0.0
    sharpe = (mean / std) * math.sqrt(len(rs)) if std > 0 else 0.0
    bars_in_market = sum(t.bars_held for t in trades if t.bars_held)
    return {
        "n_trades": len(trades),
        "n_wins": len(wins),
        "n_losses": len(losses),
        "win_rate": round(len(wins) / len(rs), 3),
        "total_r": round(sum(rs), 3),
        "avg_r": round(mean, 3),
        "gross_win_r":  round(gross_win,  3),
        "gross_loss_r": round(gross_loss, 3),  # positive number
        "profit_factor": round(pf, 3) if math.isfinite(pf) else None,
        "max_dd_r": round(max_dd, 3),
        "sharpe_like": round(sharpe, 3),
        "trades_per_100_bars": round(100 * len(rs) / max(n_bars, 1), 2),
        "exposure_pct": round(100 * bars_in_market / max(n_bars, 1), 2),
        "expectancy_r": round(mean, 3),
    }


async def run_backtest(
    symbol: str, bars_limit: int = 2000, timeframe: str = "H1",
) -> BacktestResult:
    """Fetch historical bars and run the deterministic strategy over them.

    bars_limit: H1 → ~83 days @ 1000 bars, ~166 days @ 2000, ~250 days @ 3000.
    Twelve Data Grow plan typically allows up to 5000 in one call.
    """
    symbol = symbol.upper()
    bars = await twelve_data.fetch_historical(symbol, limit=bars_limit, timeframe=timeframe)
    n = len(bars)
    if n < MIN_WARMUP_BARS + 50:
        return BacktestResult(
            symbol=symbol, timeframe=timeframe, bars_count=n,
            warmup_bars=MIN_WARMUP_BARS,
            stats={"error": f"Not enough bars: got {n}, need ≥{MIN_WARMUP_BARS+50}"},
        )

    trades: list[Trade] = []
    open_trade: Optional[Trade] = None

    for t in range(MIN_WARMUP_BARS, n):
        # 1) If a trade is open, see if THIS bar's range hits SL or TP first.
        if open_trade is not None:
            if _check_exit(open_trade, bars[t], t):
                trades.append(open_trade)
                open_trade = None
            elif (t - open_trade.entry_idx) >= MAX_BARS_HELD:
                # Force-close at this bar's close — neutral exit.
                open_trade.exit_idx = t
                open_trade.exit_price = bars[t]["close"]
                px_diff = open_trade.exit_price - open_trade.entry_price
                if open_trade.side == "SELL":
                    px_diff = -px_diff
                sl_dist = abs(open_trade.entry_price - open_trade.sl)
                open_trade.pnl_r = round(px_diff / sl_dist, 3) if sl_dist > 0 else 0.0
                open_trade.bars_held = t - open_trade.entry_idx
                open_trade.exit_reason = "TIMEOUT"
                trades.append(open_trade)
                open_trade = None

        if open_trade is not None:
            continue  # one position at a time

        # 2) Compute signal on the window ending at t (no look-ahead).
        window = bars[: t + 1]
        try:
            ind = _ind.compute_indicators(symbol, window).model_dump()
            ict = _ict.analyze(symbol, window, backtest_mode=True).model_dump()
        except Exception as e:
            logger.debug(f"analytics failed at bar {t}: {e}")
            continue

        norm = _score_bar(ind, ict)
        atr = ind.get("atr_14") or 0.0
        if atr <= 0:
            continue

        if norm >= SIGNAL_THRESHOLD:
            open_trade = _open_trade(symbol, "BUY", t, bars[t]["close"], atr)
        elif norm <= -SIGNAL_THRESHOLD:
            open_trade = _open_trade(symbol, "SELL", t, bars[t]["close"], atr)

    # End of data: close any still-open trade at last close.
    if open_trade is not None:
        last_t = n - 1
        open_trade.exit_idx = last_t
        open_trade.exit_price = bars[last_t]["close"]
        sl_dist = abs(open_trade.entry_price - open_trade.sl)
        px_diff = open_trade.exit_price - open_trade.entry_price
        if open_trade.side == "SELL":
            px_diff = -px_diff
        open_trade.pnl_r = round(px_diff / sl_dist, 3) if sl_dist > 0 else 0.0
        open_trade.bars_held = last_t - open_trade.entry_idx
        open_trade.exit_reason = "EOD"
        trades.append(open_trade)

    return BacktestResult(
        symbol=symbol, timeframe=timeframe, bars_count=n,
        warmup_bars=MIN_WARMUP_BARS,
        trades=[asdict(t) for t in trades],
        stats=_stats(trades, n - MIN_WARMUP_BARS),
    )
