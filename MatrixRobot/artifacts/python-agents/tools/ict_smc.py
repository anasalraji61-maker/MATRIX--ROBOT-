"""
ICT / SMC (Inner Circle Trader / Smart Money Concepts) analyzer.

Detects price-action / market-structure features that institutional traders
("smart money") leave on the chart, then synthesizes a bias + confluence
score that the ensemble analysis agent consumes alongside indicators / MTF.

Features detected (per symbol, on H1 bars by default):
  - Swing highs / lows (3-bar fractals)
  - BOS  (Break of Structure)  — continuation of trend
  - CHoCH (Change of Character) — first reversal break
  - Bullish / Bearish Order Blocks (last opposing candle before strong move)
  - Fair Value Gaps (FVG / imbalances) — 3-candle gaps
  - Liquidity pools: equal highs (sell-side) / equal lows (buy-side)
  - Premium / Discount / Equilibrium zone (price position in dealing range)
  - Killzone status (London 07-10 UTC, New York 12-15 UTC, Asian 23-04 UTC)
  - Final bias: bullish / bearish / neutral + confluence score in [-1, +1]

Notes:
  - Pure Python (no ML deps). Operates on raw OHLC bars provided by data_agent.
  - Designed for funded-account compliance: structure-based entries reduce
    random noise trades — every BUY has a recent CHoCH / OB / FVG to justify it.
"""
from __future__ import annotations

from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from typing import Optional


# ── Tunables (kept here so the module is self-contained) ──────────────────
SWING_LOOKBACK = 2          # fractal: bar > N left and N right neighbours
RECENT_STRUCT_BARS = 50     # how many bars back we look for BOS/CHoCH
OB_MAX_AGE_BARS = 30        # ignore order blocks older than this
FVG_MAX_AGE_BARS = 25
LIQUIDITY_EQ_TOLERANCE_PCT = 0.05   # equal highs / lows within 0.05%
PREMIUM_DISCOUNT_LOOKBACK = 50      # bars to define dealing range
KILLZONES_UTC = {
    "asian":  (23, 4),
    "london": (7, 10),
    "newyork": (12, 15),
}


# ── Data classes (small + serialisable) ───────────────────────────────────
@dataclass
class Swing:
    index: int
    price: float
    kind: str   # "high" | "low"


@dataclass
class OrderBlock:
    index: int
    high: float
    low: float
    side: str   # "bullish" | "bearish"
    age_bars: int = 0


@dataclass
class FVG:
    index: int
    top: float
    bottom: float
    side: str   # "bullish" | "bearish"
    age_bars: int = 0
    mitigated: bool = False


@dataclass
class IctAnalysis:
    symbol: str
    bias: str = "neutral"           # bullish | bearish | neutral
    score: float = 0.0              # [-1, +1]
    confluence_count: int = 0
    structure: str = "ranging"      # bullish_trend | bearish_trend | ranging
    last_event: str = "none"        # BOS_bullish | BOS_bearish | CHoCH_bullish | CHoCH_bearish | none
    last_event_age_bars: int = 999
    last_price: float = 0.0
    nearest_bullish_ob: Optional[dict] = None
    nearest_bearish_ob: Optional[dict] = None
    nearest_bullish_fvg: Optional[dict] = None
    nearest_bearish_fvg: Optional[dict] = None
    liquidity_above: Optional[float] = None      # nearest equal-highs cluster
    liquidity_below: Optional[float] = None      # nearest equal-lows cluster
    zone: str = "equilibrium"                    # premium | discount | equilibrium
    range_high: float = 0.0
    range_low: float = 0.0
    active_killzone: str = "none"                # asian | london | newyork | none
    reasons: list = field(default_factory=list)

    def model_dump(self) -> dict:
        return asdict(self)


# ── Helpers ───────────────────────────────────────────────────────────────
def _to_ohlc(bars: list[dict]) -> tuple[list[float], list[float], list[float], list[float]]:
    o = [float(b["open"]) for b in bars]
    h = [float(b["high"]) for b in bars]
    l = [float(b["low"])  for b in bars]
    c = [float(b["close"]) for b in bars]
    return o, h, l, c


def _find_swings(h: list[float], l: list[float], k: int = SWING_LOOKBACK) -> list[Swing]:
    swings: list[Swing] = []
    n = len(h)
    for i in range(k, n - k):
        if all(h[i] > h[i - j] for j in range(1, k + 1)) and all(h[i] > h[i + j] for j in range(1, k + 1)):
            swings.append(Swing(i, h[i], "high"))
        if all(l[i] < l[i - j] for j in range(1, k + 1)) and all(l[i] < l[i + j] for j in range(1, k + 1)):
            swings.append(Swing(i, l[i], "low"))
    swings.sort(key=lambda s: s.index)
    return swings


def _detect_structure(
    swings: list[Swing], c: list[float], n: int,
) -> tuple[str, str, int]:
    """
    Detect explicit break events by walking forward through closes:
      BOS_bullish — close > prior swing-high while in (or starting) bullish trend
      BOS_bearish — close < prior swing-low  while in (or starting) bearish trend
      CHoCH_bullish — first close > most recent swing-high while in bearish trend
      CHoCH_bearish — first close < most recent swing-low  while in bullish trend

    Returns (structure_label, last_event, age_bars_from_end).
    age_bars_from_end uses (n - 1 - event_bar_index).
    """
    if len(swings) < 4:
        return "ranging", "none", 999

    trend = "ranging"
    last_event = "none"
    last_event_bar = -1

    swings_sorted = sorted(swings, key=lambda s: s.index)
    # Track most recent confirmed swing high/low as we walk price forward
    last_sh: Swing | None = None
    last_sl: Swing | None = None
    swing_iter = iter(swings_sorted)
    next_swing = next(swing_iter, None)

    for i in range(n):
        # Promote swings whose index has now occurred
        while next_swing is not None and next_swing.index <= i:
            if next_swing.kind == "high":
                last_sh = next_swing
            else:
                last_sl = next_swing
            next_swing = next(swing_iter, None)

        if last_sh is None or last_sl is None:
            continue

        price = c[i]
        # Bullish break of last swing high
        if price > last_sh.price and i > last_sh.index:
            if trend == "bearish":
                last_event = "CHoCH_bullish"; last_event_bar = i
                trend = "bullish"
            else:
                last_event = "BOS_bullish"; last_event_bar = i
                trend = "bullish"
        # Bearish break of last swing low
        elif price < last_sl.price and i > last_sl.index:
            if trend == "bullish":
                last_event = "CHoCH_bearish"; last_event_bar = i
                trend = "bearish"
            else:
                last_event = "BOS_bearish"; last_event_bar = i
                trend = "bearish"

    structure = {"bullish": "bullish_trend", "bearish": "bearish_trend"}.get(trend, "ranging")
    age = (n - 1 - last_event_bar) if last_event_bar >= 0 else 999
    return structure, last_event, age


def _detect_order_blocks(o, h, l, c, swings: list[Swing], n: int) -> tuple[Optional[OrderBlock], Optional[OrderBlock]]:
    """
    Bullish OB: last DOWN candle before a strong UP move that takes out the
                most recent swing high.
    Bearish OB: last UP candle before a strong DOWN move that takes out the
                most recent swing low.
    Return (most_recent_bullish, most_recent_bearish).
    """
    bull: Optional[OrderBlock] = None
    bear: Optional[OrderBlock] = None
    # walk from recent backwards
    for i in range(n - 2, max(0, n - RECENT_STRUCT_BARS) - 1, -1):
        # bullish OB: bar i is bearish (c<o), bar i+1 closes above bar i high (strong up)
        if c[i] < o[i] and c[i + 1] > h[i] and bull is None:
            bull = OrderBlock(i, h[i], l[i], "bullish", n - 1 - i)
        # bearish OB: bar i is bullish (c>o), bar i+1 closes below bar i low (strong down)
        if c[i] > o[i] and c[i + 1] < l[i] and bear is None:
            bear = OrderBlock(i, h[i], l[i], "bearish", n - 1 - i)
        if bull and bear:
            break
    # respect max age
    if bull and bull.age_bars > OB_MAX_AGE_BARS:
        bull = None
    if bear and bear.age_bars > OB_MAX_AGE_BARS:
        bear = None
    return bull, bear


def _detect_fvgs(h, l, n: int) -> tuple[Optional[FVG], Optional[FVG]]:
    """
    3-candle imbalance:
      bullish FVG: low[i] > high[i-2]    → gap = (low[i], high[i-2])
      bearish FVG: high[i] < low[i-2]    → gap = (low[i-2], high[i])
    Return most recent of each side, ignoring mitigated ones (price has revisited).
    """
    bull: Optional[FVG] = None
    bear: Optional[FVG] = None
    start = max(2, n - FVG_MAX_AGE_BARS)
    for i in range(n - 1, start - 1, -1):
        if bull is None and l[i] > h[i - 2]:
            gap_top, gap_bot = l[i], h[i - 2]
            mitigated = any(l[j] <= gap_top and h[j] >= gap_bot for j in range(i + 1, n))
            if not mitigated:
                bull = FVG(i, gap_top, gap_bot, "bullish", n - 1 - i)
        if bear is None and h[i] < l[i - 2]:
            gap_top, gap_bot = l[i - 2], h[i]
            mitigated = any(l[j] <= gap_top and h[j] >= gap_bot for j in range(i + 1, n))
            if not mitigated:
                bear = FVG(i, gap_top, gap_bot, "bearish", n - 1 - i)
        if bull and bear:
            break
    return bull, bear


def _detect_liquidity(h, l, n: int) -> tuple[Optional[float], Optional[float]]:
    """Find clusters of equal highs (above price → sell-side liquidity) and
    equal lows (below price → buy-side liquidity)."""
    look = min(n, RECENT_STRUCT_BARS)
    recent_h = h[-look:]; recent_l = l[-look:]
    last = (h[-1] + l[-1]) / 2.0
    tol = last * (LIQUIDITY_EQ_TOLERANCE_PCT / 100.0)

    def _cluster(vals: list[float], above: bool) -> Optional[float]:
        # find any two highs/lows within tol, return one nearest to last price
        candidates: list[float] = []
        for i in range(len(vals)):
            for j in range(i + 1, len(vals)):
                if abs(vals[i] - vals[j]) <= tol:
                    candidates.append((vals[i] + vals[j]) / 2.0)
        if above:
            candidates = [v for v in candidates if v > last]
        else:
            candidates = [v for v in candidates if v < last]
        if not candidates:
            return None
        return min(candidates, key=lambda v: abs(v - last))

    return _cluster(recent_h, above=True), _cluster(recent_l, above=False)


def _premium_discount(h, l, last_close: float) -> tuple[str, float, float]:
    look = min(len(h), PREMIUM_DISCOUNT_LOOKBACK)
    hi = max(h[-look:]); lo = min(l[-look:])
    mid = (hi + lo) / 2.0
    span = hi - lo
    if span <= 0:
        return "equilibrium", hi, lo
    pos = (last_close - lo) / span
    if pos >= 0.66:
        return "premium", hi, lo
    if pos <= 0.34:
        return "discount", hi, lo
    return "equilibrium", hi, lo


def _active_killzone(now_utc: Optional[datetime] = None) -> str:
    now = now_utc or datetime.now(timezone.utc)
    hour = now.hour
    for name, (start, end) in KILLZONES_UTC.items():
        if start <= end:
            if start <= hour < end:
                return name
        else:  # wraps midnight, e.g. asian 23..4
            if hour >= start or hour < end:
                return name
    return "none"


# ── Public API ────────────────────────────────────────────────────────────
def analyze(symbol: str, bars: list[dict], backtest_mode: bool = False) -> IctAnalysis:
    """Run the full ICT/SMC analysis on the given OHLC bar series.

    backtest_mode=True disables wall-clock-dependent behaviour (killzone
    amplification + `ict_killzones_only` gate) so historical replays are
    deterministic across re-runs."""
    if not bars or len(bars) < 20:
        return IctAnalysis(symbol=symbol, reasons=["Insufficient bars for ICT/SMC"])

    o, h, l, c = _to_ohlc(bars)
    n = len(c)
    last_close = c[-1]

    swings = _find_swings(h, l)
    structure, last_event, event_age = _detect_structure(swings, c, n)
    bull_ob, bear_ob = _detect_order_blocks(o, h, l, c, swings, n)
    bull_fvg, bear_fvg = _detect_fvgs(h, l, n)
    liq_above, liq_below = _detect_liquidity(h, l, n)
    zone, range_hi, range_lo = _premium_discount(h, l, last_close)
    kz = "none" if backtest_mode else _active_killzone()

    # ── Confluence scoring ────────────────────────────────────────────
    score = 0.0
    reasons: list[str] = []
    conf = 0

    # Structure: heaviest weight
    if last_event == "CHoCH_bullish":
        score += 0.45; conf += 1; reasons.append("CHoCH bullish — trend reversal up")
    elif last_event == "CHoCH_bearish":
        score -= 0.45; conf += 1; reasons.append("CHoCH bearish — trend reversal down")
    elif last_event == "BOS_bullish":
        score += 0.30; conf += 1; reasons.append("BOS bullish — trend continuation up")
    elif last_event == "BOS_bearish":
        score -= 0.30; conf += 1; reasons.append("BOS bearish — trend continuation down")

    # Order blocks — price reacting / sitting in OB
    if bull_ob and bull_ob.low <= last_close <= bull_ob.high * 1.001:
        score += 0.20; conf += 1
        reasons.append(f"Price in bullish OB ({bull_ob.low:.5f}–{bull_ob.high:.5f})")
    if bear_ob and bear_ob.low * 0.999 <= last_close <= bear_ob.high:
        score -= 0.20; conf += 1
        reasons.append(f"Price in bearish OB ({bear_ob.low:.5f}–{bear_ob.high:.5f})")

    # FVG — price reacting / sitting in FVG
    if bull_fvg and bull_fvg.bottom <= last_close <= bull_fvg.top:
        score += 0.15; conf += 1
        reasons.append(f"Price in bullish FVG ({bull_fvg.bottom:.5f}–{bull_fvg.top:.5f})")
    if bear_fvg and bear_fvg.bottom <= last_close <= bear_fvg.top:
        score -= 0.15; conf += 1
        reasons.append(f"Price in bearish FVG ({bear_fvg.bottom:.5f}–{bear_fvg.top:.5f})")

    # Premium/Discount — sells in premium, buys in discount
    if zone == "discount":
        score += 0.10; reasons.append("Discount zone — favours buys")
    elif zone == "premium":
        score -= 0.10; reasons.append("Premium zone — favours sells")

    # Liquidity grab opportunity: liquidity below + bullish bias = sweep then up
    if liq_below and last_close > liq_below and structure == "bullish_trend":
        score += 0.05; reasons.append(f"Buy-side liquidity at {liq_below:.5f} swept")
    if liq_above and last_close < liq_above and structure == "bearish_trend":
        score -= 0.05; reasons.append(f"Sell-side liquidity at {liq_above:.5f} swept")

    # Killzone amplifier (only if not neutral)
    if kz in ("london", "newyork") and abs(score) >= 0.20:
        score *= 1.15
        reasons.append(f"In {kz.upper()} killzone — amplified conviction")

    score = max(-1.0, min(1.0, round(score, 3)))

    # Apply config gates: killzones-only + minimum confluence
    try:
        from config import get_settings
        cfg = get_settings()
        if cfg.ict_killzones_only and kz == "none" and not backtest_mode:
            score = 0.0
            reasons.append("Outside killzone — bias suppressed (ict_killzones_only)")
        if conf < cfg.ict_min_confluence:
            score = 0.0
            reasons.append(f"Confluence {conf} < min {cfg.ict_min_confluence} — bias suppressed")
    except Exception:
        pass

    if score >= 0.25:
        bias = "bullish"
    elif score <= -0.25:
        bias = "bearish"
    else:
        bias = "neutral"

    return IctAnalysis(
        symbol=symbol,
        bias=bias,
        score=score,
        confluence_count=conf,
        structure=structure,
        last_event=last_event,
        last_event_age_bars=event_age,
        last_price=round(last_close, 5),
        nearest_bullish_ob=asdict(bull_ob) if bull_ob else None,
        nearest_bearish_ob=asdict(bear_ob) if bear_ob else None,
        nearest_bullish_fvg=asdict(bull_fvg) if bull_fvg else None,
        nearest_bearish_fvg=asdict(bear_fvg) if bear_fvg else None,
        liquidity_above=round(liq_above, 5) if liq_above else None,
        liquidity_below=round(liq_below, 5) if liq_below else None,
        zone=zone,
        range_high=round(range_hi, 5),
        range_low=round(range_lo, 5),
        active_killzone=kz,
        reasons=reasons[:6],
    )


def format_summary(ict: IctAnalysis) -> str:
    return (
        f"ICT[{ict.symbol}]: {ict.bias.upper()} score={ict.score:+.2f} "
        f"struct={ict.structure} evt={ict.last_event} zone={ict.zone} kz={ict.active_killzone} "
        f"conf={ict.confluence_count}"
    )
