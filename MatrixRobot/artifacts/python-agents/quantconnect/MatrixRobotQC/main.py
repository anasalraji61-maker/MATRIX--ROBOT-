# region imports
from AlgorithmImports import *
from datetime import timedelta
import math
# endregion

# =============================================================================
# Matrix Robot V11 - FULL backtestable stack for QuantConnect (single file)
# Ported: ensemble, ICT, MTF, session, volatility, council, risk, prop,
#         emergency, correlation, scalp-simplified, supervisor
# NOT in QC (other platforms): GPT/agentic_brain, MT5 bridge, VPS logs, memory
# =============================================================================

MATRIX_SYMBOLS = (
    "EURUSD", "GBPUSD", "USDJPY", "USDCHF", "AUDUSD", "NZDUSD", "USDCAD",
    "EURGBP", "EURJPY", "GBPJPY", "EURAUD", "EURCHF", "AUDJPY", "CHFJPY",
    "CADJPY", "NZDJPY", "GBPCHF", "AUDCAD", "AUDNZD",
    "XAUUSD", "XAGUSD",
)

# Matrix config defaults (FN_CHALLENGE profile) — QC Round 3: fewer/higher-quality trades
MIN_WARMUP = 220
MAX_BARS_HELD = 48
SIGNAL_NORM_THRESHOLD = 0.32  # was 0.25 — fewer ensemble signals
SL_ATR_MULT = 1.5
TP_RR = 2.0
MIN_STRENGTH = 0.68  # was 0.60
NORMAL_STRENGTH = 0.75  # was 0.68
SMALL_STRENGTH = 0.68
META_SCORE_MIN = 0.28  # was 0.15 — tighter council
MAX_CONCURRENT = 3  # was 7 — QC Free order budget
MAX_TRADES_DAY = 10  # was 60 — stay under ~10k orders
DAILY_DD_LIMIT = 4.0
TOTAL_DD_LIMIT = 9.0
ICT_WEIGHT = 3.5
MTF_WEIGHT = 3.0
MAX_CORR_SAME_CCY = 4  # QC audit: was 3
OFF_SESSION_SMALL_GATE = False  # QC backtest: disable off-session small gate
BACKTEST_SOFT_EMERGENCY = True  # QC: daily lock resets each day (no permanent peak-recovery lock)
BACKTEST_SOFT_TOTAL_DD = True  # QC: do not permanently reject on peak total_dd (Joker round 2)
QC_MIN_EQUITY_FRAC = 0.70  # stop new entries if equity < 70% of start (QC soft)
RISK_PCT_PER_TRADE = 0.25  # was 0.5 — smaller size
# QC verify window (Joker Round 3): 1 year first — avoid 10k order cap
QC_START = (2023, 1, 1)
QC_END = (2024, 1, 1)

ENSEMBLE_W = {
    "rsi": 1.5, "stoch": 1.0, "williams": 0.8, "macd": 1.5,
    "ema_stack": 2.0, "ema200": 1.0, "adx": 1.5, "ichimoku": 1.2,
    "mtf": 3.0, "ict": 3.5, "sentiment": 1.0,
    "near_support": 1.2, "near_resistance": 1.2,
}

COUNCIL_W = {
    "market_regime": 0.12, "technical_quant": 0.18, "ict_price_action": 0.15,
    "scalping": 0.12, "news_macro": 0.10, "strategy_router": 0.13,
    "skeptic": 0.12, "risk_prop": 0.08,
}

KILLZONES = {"asian": (23, 4), "london": (7, 10), "newyork": (12, 15)}


# --- indicator helpers (pure Python, no pandas) ---

def _ema(series, period):
    if len(series) < period:
        return None
    k = 2.0 / (period + 1)
    v = sum(series[:period]) / period
    for x in series[period:]:
        v = x * k + v * (1 - k)
    return v


def _rsi(closes, period=14):
    if len(closes) < period + 1:
        return None
    gains, losses = [], []
    for i in range(1, len(closes)):
        d = closes[i] - closes[i - 1]
        gains.append(max(d, 0))
        losses.append(max(-d, 0))
    avg_g = sum(gains[-period:]) / period
    avg_l = sum(losses[-period:]) / period
    if avg_l == 0:
        return 100.0
    rs = avg_g / avg_l
    return 100 - (100 / (1 + rs))


def _atr(highs, lows, closes, period=14):
    if len(closes) < period + 1:
        return None
    trs = []
    for i in range(1, len(closes)):
        tr = max(highs[i] - lows[i], abs(highs[i] - closes[i - 1]), abs(lows[i] - closes[i - 1]))
        trs.append(tr)
    return sum(trs[-period:]) / period if len(trs) >= period else None


def _macd_hist(closes):
    if len(closes) < 35:
        return None
    ema12 = _ema(closes, 12)
    ema26 = _ema(closes, 26)
    if ema12 is None or ema26 is None:
        return None
    macd = ema12 - ema26
    # signal approx
    macd_line = []
    for i in range(26, len(closes) + 1):
        e12 = _ema(closes[:i], 12)
        e26 = _ema(closes[:i], 26)
        if e12 and e26:
            macd_line.append(e12 - e26)
    if len(macd_line) < 9:
        return macd - macd
    sig = _ema(macd_line, 9)
    return macd - sig if sig else macd


def _stoch_k(highs, lows, closes, period=14):
    if len(closes) < period:
        return None
    hh = max(highs[-period:])
    ll = min(lows[-period:])
    if hh == ll:
        return 50.0
    return 100 * (closes[-1] - ll) / (hh - ll)


def _williams_r(highs, lows, closes, period=14):
    if len(closes) < period:
        return None
    hh = max(highs[-period:])
    ll = min(lows[-period:])
    if hh == ll:
        return -50.0
    return -100 * (hh - closes[-1]) / (hh - ll)


def _adx(highs, lows, closes, period=14):
    if len(closes) < period + 2:
        return None, None, None
    plus_dm, minus_dm, tr_list = [], [], []
    for i in range(1, len(closes)):
        up = highs[i] - highs[i - 1]
        down = lows[i - 1] - lows[i]
        plus_dm.append(up if up > down and up > 0 else 0)
        minus_dm.append(down if down > up and down > 0 else 0)
        tr = max(highs[i] - lows[i], abs(highs[i] - closes[i - 1]), abs(lows[i] - closes[i - 1]))
        tr_list.append(tr)
    if len(tr_list) < period:
        return None, None, None
    atr_v = sum(tr_list[-period:]) / period
    if atr_v == 0:
        return 0, 0, 0
    di_p = 100 * (sum(plus_dm[-period:]) / period) / atr_v
    di_m = 100 * (sum(minus_dm[-period:]) / period) / atr_v
    dx = 100 * abs(di_p - di_m) / (di_p + di_m) if (di_p + di_m) else 0
    return dx, di_p, di_m


def compute_indicators(bars):
    if len(bars) < 50:
        return {}
    o = [b["open"] for b in bars]
    h = [b["high"] for b in bars]
    l = [b["low"] for b in bars]
    c = [b["close"] for b in bars]
    ema20 = _ema(c, 20)
    ema50 = _ema(c, 50)
    ema200 = _ema(c, 200) if len(c) >= 200 else None
    bb_mid = sum(c[-20:]) / 20
    std = math.sqrt(sum((x - bb_mid) ** 2 for x in c[-20:]) / 20) if len(c) >= 20 else 0
    bb_up = bb_mid + 2 * std
    bb_lo = bb_mid - 2 * std
    bb_width = (bb_up - bb_lo) / bb_mid * 100 if bb_mid else 0
    atr = _atr(h, l, c, 14)
    swing_lo = min(l[-50:])
    swing_hi = max(h[-50:])
    ich = None
    if ema200:
        tenkan = (max(h[-9:]) + min(l[-9:])) / 2
        kijun = (max(h[-26:]) + min(l[-26:])) / 2
        sa = (tenkan + kijun) / 2
        sb = (max(h[-52:]) + min(l[-52:])) / 2
        top, bot = max(sa, sb), min(sa, sb)
        if c[-1] > top:
            ich = True
        elif c[-1] < bot:
            ich = False
    adx, dip, dim = _adx(h, l, c, 14)
    return {
        "rsi_14": _rsi(c, 14),
        "stoch_k": _stoch_k(h, l, c, 14),
        "williams_r": _williams_r(h, l, c, 14),
        "macd_hist": _macd_hist(c),
        "ema_20": ema20, "ema_50": ema50, "ema_200": ema200,
        "bb_mid": bb_mid, "bb_width_pct": bb_width,
        "atr_14": atr, "adx_14": adx, "di_plus": dip, "di_minus": dim,
        "ichimoku_above_cloud": ich,
        "support": swing_lo, "resistance": swing_hi,
    }


# --- ICT / SMC (from tools/ict_smc.py) ---

def _ict_killzone(hour):
    for name, (start, end) in KILLZONES.items():
        if start <= end:
            if start <= hour < end:
                return name
        else:
            if hour >= start or hour < end:
                return name
    return "none"


def analyze_ict(bars, bar_time):
    if len(bars) < 20:
        return {"bias": "neutral", "score": 0.0, "confluence_count": 0,
                "structure": "ranging", "last_event": "none", "zone": "equilibrium",
                "active_killzone": "none"}
    h = [b["high"] for b in bars]
    l = [b["low"] for b in bars]
    c = [b["close"] for b in bars]
    o = [b["open"] for b in bars]
    n = len(c)
    last = c[-1]
    # swings
    swings = []
    k = 2
    for i in range(k, n - k):
        if all(h[i] > h[i - j] for j in range(1, k + 1)) and all(h[i] > h[i + j] for j in range(1, k + 1)):
            swings.append((i, h[i], "high"))
        if all(l[i] < l[i - j] for j in range(1, k + 1)) and all(l[i] < l[i + j] for j in range(1, k + 1)):
            swings.append((i, l[i], "low"))
    trend = "ranging"
    last_event = "none"
    if len(swings) >= 4:
        last_sh = [s for s in swings if s[2] == "high"]
        last_sl = [s for s in swings if s[2] == "low"]
        if last_sh and last_sl:
            if last > last_sh[-1][1]:
                last_event = "BOS_bullish" if trend != "bearish" else "CHoCH_bullish"
                trend = "bullish"
            elif last < last_sl[-1][1]:
                last_event = "BOS_bearish" if trend != "bullish" else "CHoCH_bearish"
                trend = "bearish"
    score = 0.0
    conf = 0
    if "CHoCH_bullish" in last_event:
        score += 0.45; conf += 1
    elif "CHoCH_bearish" in last_event:
        score -= 0.45; conf += 1
    elif "BOS_bullish" in last_event:
        score += 0.30; conf += 1
    elif "BOS_bearish" in last_event:
        score -= 0.30; conf += 1
    rh, rl = max(h[-50:]), min(l[-50:])
    zone = "equilibrium"
    if last < (rh + rl) / 2:
        zone = "discount"; score += 0.10
    elif last > (rh + rl) / 2:
        zone = "premium"; score -= 0.10
    kz = _ict_killzone(bar_time.hour) if bar_time else "none"
    if kz in ("london", "newyork") and abs(score) >= 0.20:
        score *= 1.15
    score = max(-1.0, min(1.0, score))
    bias = "bullish" if score >= 0.25 else ("bearish" if score <= -0.25 else "neutral")
    return {
        "bias": bias, "score": score, "confluence_count": conf,
        "structure": trend + "_trend" if trend != "ranging" else "ranging",
        "last_event": last_event, "zone": zone, "active_killzone": kz,
        "bos": "BOS" in last_event, "choch": "CHoCH" in last_event,
    }


def compute_mtf(bars):
    c = [b["close"] for b in bars]
    if len(c) < 100:
        return {"score": 0.0, "aligned_count": 0, "consensus": "neutral"}
    trends = []
    for lb in (4, 24, 96):
        if len(c) > lb:
            trends.append(1 if c[-1] > c[-lb] else -1)
    if not trends:
        return {"score": 0.0, "aligned_count": 0, "consensus": "neutral"}
    s = sum(trends) / len(trends)
    aligned = sum(1 for t in trends if t == (1 if s > 0 else -1)) if s != 0 else 0
    cons = "bullish" if s > 0.3 else ("bearish" if s < -0.3 else "neutral")
    return {"score": s, "aligned_count": aligned, "consensus": cons}


def vol_regime(ind):
    atr = ind.get("atr_14") or 0
    close = ind.get("bb_mid") or 1
    pct = atr / close * 100 if close else 0
    if pct > 0.15:
        return {"regime": "high", "size_multiplier": 0.85}
    if pct < 0.05:
        return {"regime": "low", "size_multiplier": 0.9}
    return {"regime": "normal", "size_multiplier": 1.0}


def session_profile(bar_time):
    kz = _ict_killzone(bar_time.hour) if bar_time else "none"
    return {
        "active_killzone": kz,
        "liquidity": "high" if kz in ("london", "newyork") else "low",
        "news_blackout": False,
    }


# --- Ensemble (analysis_agent) ---

def ensemble_analysis(symbol, ind, mtf, ict, vol, sentiment):
    score = 0.0
    rsi = ind.get("rsi_14")
    if rsi is not None:
        if rsi < 35: score += ENSEMBLE_W["rsi"]
        elif rsi > 65: score -= ENSEMBLE_W["rsi"]
    sk = ind.get("stoch_k")
    if sk is not None:
        if sk < 20: score += ENSEMBLE_W["stoch"]
        elif sk > 80: score -= ENSEMBLE_W["stoch"]
    wr = ind.get("williams_r")
    if wr is not None:
        if wr < -80: score += ENSEMBLE_W["williams"]
        elif wr > -20: score -= ENSEMBLE_W["williams"]
    mh = ind.get("macd_hist")
    if mh is not None:
        score += ENSEMBLE_W["macd"] if mh > 0 else -ENSEMBLE_W["macd"]
    e20, e50, e200 = ind.get("ema_20"), ind.get("ema_50"), ind.get("ema_200")
    if e20 and e50:
        score += ENSEMBLE_W["ema_stack"] if e20 > e50 else -ENSEMBLE_W["ema_stack"]
    if e200 and ind.get("bb_mid"):
        score += ENSEMBLE_W["ema200"] if ind["bb_mid"] > e200 else -ENSEMBLE_W["ema200"]
    adx, dip, dim = ind.get("adx_14"), ind.get("di_plus"), ind.get("di_minus")
    if adx and adx >= 25 and dip is not None and dim is not None:
        score += ENSEMBLE_W["adx"] if dip > dim else -ENSEMBLE_W["adx"]
    ich = ind.get("ichimoku_above_cloud")
    if ich is True: score += ENSEMBLE_W["ichimoku"]
    elif ich is False: score -= ENSEMBLE_W["ichimoku"]
    ms = float(mtf.get("score", 0) or 0)
    if abs(ms) >= 0.25:
        score += ENSEMBLE_W["mtf"] * ms
    ics = float(ict.get("score", 0) or 0)
    if abs(ics) >= 0.20:
        score += ICT_WEIGHT * ics
    max_s = sum(ENSEMBLE_W.values())
    norm = max(-1.0, min(1.0, score / max_s))
    vm = float(vol.get("size_multiplier", 1.0) or 1.0)
    if norm >= SIGNAL_NORM_THRESHOLD:
        sig = "BUY"
        strength = round(min(0.5 + abs(norm) * 0.7, 0.97) * (0.85 + 0.15 * vm), 3)
    elif norm <= -SIGNAL_NORM_THRESHOLD:
        sig = "SELL"
        strength = round(min(0.5 + abs(norm) * 0.7, 0.97) * (0.85 + 0.15 * vm), 3)
    else:
        sig, strength = "HOLD", 0.3
    return {"symbol": symbol, "signal": sig, "strength": strength, "norm": norm}


# --- Council ---

def _clamp(v):
    return max(-1.0, min(1.0, round(v, 3)))


def council_brains(state, cand):
    sym = cand["symbol"]
    sig = cand["signal"]
    ind = state["indicators"].get(sym, {})
    ict = state["ict"].get(sym, {})
    mtf = state["mtf"].get(sym, {})
    sess = state["session"]
    vol = state["volatility"].get(sym, {})
    strength = float(cand.get("strength", 0))

    brains = []

    # market_regime
    kz = sess.get("active_killzone", "none")
    sc = 0.0
    if kz in ("london", "newyork"): sc += 0.25
    elif kz == "asian": sc += 0.1
    else: sc -= 0.1
    if vol.get("regime") == "high": sc += 0.35
    veto = sess.get("news_blackout", False)
    brains.append({"brain": "market_regime", "score": _clamp(-0.8 if veto else sc),
                   "veto": veto, "veto_reason": "news blackout" if veto else ""})

    # technical_quant
    tsc = strength - 0.5
    rsi = float(ind.get("rsi_14") or 50)
    if sig == "BUY" and rsi < 65: tsc += 0.2
    if sig == "SELL" and rsi > 35: tsc += 0.2
    mh = ind.get("macd_hist") or 0
    if sig == "BUY" and mh > 0: tsc += 0.15
    if sig == "SELL" and mh < 0: tsc += 0.15
    tsc += min(0.15, int(mtf.get("aligned_count", 0)) * 0.05)
    brains.append({"brain": "technical_quant", "score": _clamp(tsc), "veto": False, "veto_reason": ""})

    # ict_price_action
    bias = str(ict.get("bias", "neutral"))
    isc = 0.0
    if sig == "BUY" and "bull" in bias: isc = 0.45
    elif sig == "SELL" and "bear" in bias: isc = 0.45
    elif bias != "neutral": isc = -0.35
    isc += min(0.25, int(ict.get("confluence_count", 0)) * 0.08)
    brains.append({"brain": "ict_price_action", "score": _clamp(isc), "veto": False, "veto_reason": ""})

    # scalping
    ssc = 0.1 if kz in ("london", "newyork") and strength >= 0.65 else -0.1
    brains.append({"brain": "scalping", "score": _clamp(ssc), "veto": False, "veto_reason": ""})

    # news_macro (neutral in backtest - no live feed)
    brains.append({"brain": "news_macro", "score": 0.0, "veto": False, "veto_reason": ""})

    # strategy_router
    rsc = 0.2 if vol.get("regime") == "normal" else 0.0
    brains.append({"brain": "strategy_router", "score": _clamp(rsc), "veto": False, "veto_reason": ""})

    # skeptic
    skc = -0.2 if strength < 0.65 else 0.1
    brains.append({"brain": "skeptic", "score": _clamp(skc), "veto": False, "veto_reason": ""})

    # risk_prop
    rpsc = 0.15
    veto_r = False
    if state.get("daily_dd", 0) >= DAILY_DD_LIMIT * 0.75:
        rpsc = -0.5; veto_r = True
    brains.append({"brain": "risk_prop", "score": _clamp(rpsc), "veto": veto_r,
                   "veto_reason": "DD approaching limit" if veto_r else ""})

    return brains


def meta_judge(brains, cand):
    total_w = weighted = 0.0
    vetoes = []
    for b in brains:
        w = COUNCIL_W.get(b["brain"], 0.1)
        weighted += b["score"] * w
        total_w += w
        if b.get("veto"):
            vetoes.append(b["brain"] + ": " + (b.get("veto_reason") or ""))
    meta_score = weighted / total_w if total_w else 0.0
    hard_veto = any(b.get("veto") for b in brains)
    sig = cand["signal"]
    final = "HOLD"
    if not hard_veto and meta_score >= META_SCORE_MIN and meta_score >= -0.2 and sig in ("BUY", "SELL"):
        final = sig
    approved = final in ("BUY", "SELL") and not vetoes and meta_score >= META_SCORE_MIN
    return {"meta_score": _clamp(meta_score), "final_action": final,
            "approved": approved, "vetoes": vetoes}


# --- Risk / tiers / prop ---

def classify_tier(strength):
    if strength < SMALL_STRENGTH:
        return "HOLD"
    if strength >= NORMAL_STRENGTH:
        return "NORMAL"
    return "SMALL"


def risk_approve(state, cand, council_ok):
    sym = cand["symbol"]
    strength = float(cand["strength"])
    tier = classify_tier(strength)
    reasons = []
    if not council_ok:
        reasons.append("council rejected")
    if tier == "HOLD":
        reasons.append("strength below tier minimum")
    if strength < MIN_STRENGTH:
        reasons.append("below min conviction " + str(MIN_STRENGTH))
    if state.get("daily_dd", 0) >= DAILY_DD_LIMIT:
        reasons.append("daily DD limit")
    # QC soft mode: skip permanent total_dd lock so trading continues after first ~9% peak DD
    if not BACKTEST_SOFT_TOTAL_DD and state.get("total_dd", 0) >= TOTAL_DD_LIMIT:
        reasons.append("total DD limit")
    if state.get("emergency_locked"):
        reasons.append("emergency lockout")
    if state.get("equity_frac", 1.0) < QC_MIN_EQUITY_FRAC:
        reasons.append("equity soft floor " + str(QC_MIN_EQUITY_FRAC))
    if len(state.get("open_positions", [])) >= MAX_CONCURRENT:
        reasons.append("max concurrent positions")
    if state.get("trades_today", 0) >= MAX_TRADES_DAY:
        reasons.append("max trades per day")
    if not correlation_ok(state, sym, cand["signal"]):
        reasons.append("correlation exposure cap")
    sess = state.get("session", {})
    if OFF_SESSION_SMALL_GATE and sess.get("active_killzone") == "none" and tier == "SMALL" and strength < 0.80:
        reasons.append("off-session small gate")
    return len(reasons) == 0, reasons


def correlation_ok(state, sym, signal):
    base = sym[:3]
    quote = sym[3:6] if len(sym) >= 6 else ""
    same = 0
    for p in state.get("open_positions", []):
        ps = p["symbol"]
        if signal == "BUY" and ps.endswith(quote):
            same += 1
        if signal == "SELL" and ps.startswith(base):
            same += 1
    return same < MAX_CORR_SAME_CCY


# --- Scalp simplified (testable path) ---

def scalp_signal(cand, ict, sess):
    if cand["signal"] not in ("BUY", "SELL"):
        return None
    if float(cand["strength"]) < 0.72:
        return None
    if sess.get("active_killzone") not in ("london", "newyork"):
        return None
    if int(ict.get("confluence_count", 0)) < 1:
        return None
    return {"mode": "SCALP", "signal": cand["signal"], "sl_mult": 1.0, "tp_mult": 1.2}


class _BarView(object):
    def __init__(self, o, h, l, c):
        self.Open, self.High, self.Low, self.Close = o, h, l, c


class MatrixRobotQC(QCAlgorithm):

    def Initialize(self):
        self.SetStartDate(*QC_START)
        self.SetEndDate(*QC_END)
        self.SetCash(100000)
        # Default brokerage for QC backtest (avoids OANDA MarketOnOpen errors)
        self.SetBrokerageModel(BrokerageName.Default)

        self._symbols = []
        for t in MATRIX_SYMBOLS:
            try:
                s = self.AddForex(t, Resolution.Hour, Market.OANDA).Symbol
                self._symbols.append(s)
            except Exception:
                self.Debug("Skip symbol: " + t)

        self.SetWarmUp(MIN_WARMUP, Resolution.Hour)

        self._windows = {}
        self._open = {}
        self._stats = {
            "ensemble_signals": 0, "council_approved": 0, "council_rejected": 0,
            "risk_approved": 0, "risk_rejected": 0, "trades_closed": 0,
            "wins": 0, "losses": 0, "total_r": 0.0,
            "risk_reject_reasons": {},
            "emergency_lock_days": 0,
        }
        self._trades_today = 0
        self._last_day = None
        self._peak_equity = 100000.0
        self._day_start_equity = 100000.0
        self._start_equity = 100000.0
        self._emergency_locked = False
        self._emergency_locked_today = False

    def _read_bar(self, data, sym):
        if data.Bars.ContainsKey(sym):
            b = data.Bars[sym]
            return _BarView(float(b.Open), float(b.High), float(b.Low), float(b.Close))
        if data.QuoteBars.ContainsKey(sym):
            qb = data.QuoteBars[sym]
            return _BarView(
                float((qb.Bid.Open + qb.Ask.Open) / 2),
                float((qb.Bid.High + qb.Ask.High) / 2),
                float((qb.Bid.Low + qb.Ask.Low) / 2),
                float((qb.Bid.Close + qb.Ask.Close) / 2),
            )
        return None

    def _update_dd(self):
        eq = float(self.Portfolio.TotalPortfolioValue)
        self._peak_equity = max(self._peak_equity, eq)
        total_dd = (self._peak_equity - eq) / self._peak_equity * 100 if self._peak_equity else 0
        daily_dd = (self._day_start_equity - eq) / self._day_start_equity * 100 if self._day_start_equity else 0
        if daily_dd < 0:
            daily_dd = 0
        if daily_dd >= DAILY_DD_LIMIT and not self._emergency_locked_today:
            self._emergency_locked = True
            self._emergency_locked_today = True
            self._stats["emergency_lock_days"] += 1
        return daily_dd, total_dd

    def _check_exits(self, sym, bar):
        if sym not in self._open:
            return
        t = self._open[sym]
        hi, lo = float(bar.High), float(bar.Low)
        hit_sl = (lo <= t["sl"]) if t["side"] == "BUY" else (hi >= t["sl"])
        hit_tp = (hi >= t["tp"]) if t["side"] == "BUY" else (lo <= t["tp"])
        closed = False
        pnl_r = 0.0
        if hit_sl and hit_tp:
            t["exit"] = t["sl"]; pnl_r = -1.0; closed = True
        elif hit_sl:
            t["exit"] = t["sl"]; pnl_r = -1.0; closed = True
        elif hit_tp:
            t["exit"] = t["tp"]; pnl_r = TP_RR; closed = True
        elif t["bars"] >= MAX_BARS_HELD:
            t["exit"] = float(bar.Close); sl_d = abs(t["entry"] - t["sl"])
            diff = float(bar.Close) - t["entry"]
            if t["side"] == "SELL":
                diff = -diff
            pnl_r = diff / sl_d if sl_d else 0; closed = True
        else:
            t["bars"] += 1
        if closed:
            self._stats["trades_closed"] += 1
            self._stats["total_r"] += pnl_r
            if pnl_r > 0: self._stats["wins"] += 1
            else: self._stats["losses"] += 1
            if sym in self.Portfolio and self.Portfolio[sym].Invested:
                self.Liquidate(sym)
            del self._open[sym]

    def OnData(self, data):
        warming = self.IsWarmingUp

        if not warming:
            today = self.Time.date()
            if self._last_day != today:
                self._last_day = today
                self._trades_today = 0
                self._day_start_equity = float(self.Portfolio.TotalPortfolioValue)
                self._emergency_locked_today = False
                if BACKTEST_SOFT_EMERGENCY:
                    # QC: daily DD lock applies same-day only; fresh day resumes trading
                    self._emergency_locked = False
                elif self._emergency_locked and self._day_start_equity >= self._peak_equity * 0.99:
                    self._emergency_locked = False

            daily_dd, total_dd = self._update_dd()
        else:
            daily_dd, total_dd = 0.0, 0.0

        open_list = [{"symbol": str(k).split(" ")[0].replace("/", ""), "side": v["side"]}
                     for k, v in self._open.items()]

        for sym in self._symbols:
            bar = self._read_bar(data, sym)
            if bar is None:
                continue
            if not warming:
                self._check_exits(sym, bar)

            w = self._windows.setdefault(sym, [])
            w.append({
                "open": float(bar.Open), "high": float(bar.High),
                "low": float(bar.Low), "close": float(bar.Close),
                "volume": 0.0,
            })
            if len(w) > 500:
                w = w[-500:]
                self._windows[sym] = w
            if warming or len(w) < MIN_WARMUP:
                continue
            if sym in self._open:
                continue

            ticker = str(sym).split(" ")[0].replace("/", "")
            ind = compute_indicators(w)
            ict = analyze_ict(w, self.Time)
            mtf = compute_mtf(w)
            vol = vol_regime(ind)
            sess = session_profile(self.Time)
            sentiment = {"label": "NEUTRAL", "score": 0.0}

            state = {
                "indicators": {ticker: ind},
                "ict": {ticker: ict},
                "mtf": {ticker: mtf},
                "volatility": {ticker: vol},
                "session": sess,
                "daily_dd": daily_dd,
                "total_dd": total_dd,
                "emergency_locked": self._emergency_locked,
                "open_positions": open_list,
                "trades_today": self._trades_today,
                "equity_frac": float(self.Portfolio.TotalPortfolioValue) / self._start_equity,
            }

            cand = ensemble_analysis(ticker, ind, mtf, ict, vol, sentiment)
            if cand["signal"] == "HOLD":
                continue
            self._stats["ensemble_signals"] += 1

            brains = council_brains(state, cand)
            meta = meta_judge(brains, cand)
            if not meta["approved"]:
                self._stats["council_rejected"] += 1
                continue
            self._stats["council_approved"] += 1

            ok, rej = risk_approve(state, cand, True)
            if not ok:
                self._stats["risk_rejected"] += 1
                for r in rej:
                    rr = self._stats["risk_reject_reasons"]
                    rr[r] = rr.get(r, 0) + 1
                continue
            self._stats["risk_approved"] += 1

            scalp = scalp_signal(cand, ict, sess)
            atr = ind.get("atr_14") or float(bar.Close) * 0.001
            sl_mult = SL_ATR_MULT
            tp_mult = TP_RR
            if scalp:
                sl_mult = scalp["sl_mult"]
                tp_mult = scalp["tp_mult"]

            price = float(bar.Close)
            sl_dist = max(atr * sl_mult, price * 0.0005)
            if cand["signal"] == "BUY":
                sl, tp = price - sl_dist, price + sl_dist * tp_mult
                self.MarketOrder(sym, self._lot_size(sym, sl_dist))
            else:
                sl, tp = price + sl_dist, price - sl_dist * tp_mult
                self.MarketOrder(sym, -self._lot_size(sym, sl_dist))

            self._open[sym] = {
                "side": cand["signal"], "entry": price, "sl": sl, "tp": tp,
                "bars": 0, "scalp": scalp is not None,
            }
            self._trades_today += 1

    def _lot_size(self, sym, sl_dist):
        risk_pct = RISK_PCT_PER_TRADE
        eq = float(self.Portfolio.TotalPortfolioValue)
        risk_cash = eq * risk_pct / 100.0
        if sl_dist <= 0:
            return 1000
        units = int(risk_cash / sl_dist)
        return max(1000, min(units, 100000))

    def OnEndOfAlgorithm(self):
        s = self._stats
        n = s["trades_closed"]
        wr = s["wins"] / n if n else 0
        pf = s["wins"] * TP_RR / s["losses"] if s["losses"] else 0
        report = (
            "=== MATRIX QC FULL REPORT === | "
            "Symbols: " + str(len(self._symbols)) + " | "
            "Ensemble: " + str(s["ensemble_signals"]) + " | "
            "Council ok: " + str(s["council_approved"]) + " | "
            "Council rej: " + str(s["council_rejected"]) + " | "
            "Risk ok: " + str(s["risk_approved"]) + " | "
            "Risk rej: " + str(s["risk_rejected"]) + " | "
            "Trades: " + str(n) + " | "
            "WR: " + str(round(wr, 3)) + " | "
            "PF(R): " + str(round(pf, 3)) + " | "
            "Total R: " + str(round(s["total_r"], 3)) + " | "
            "Emergency lock days: " + str(s["emergency_lock_days"]) + " | "
            "SoftEmerg=" + str(BACKTEST_SOFT_EMERGENCY) + " | "
            "SoftTotalDD=" + str(BACKTEST_SOFT_TOTAL_DD)
        )
        self.Log(report)
        for reason, count in sorted(s["risk_reject_reasons"].items(), key=lambda x: -x[1]):
            self.Log("Risk reject: " + reason + " = " + str(count))
