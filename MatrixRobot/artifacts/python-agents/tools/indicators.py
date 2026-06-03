"""
Technical indicator suite — computes a rich feature set per symbol.

Adds beyond the baseline (RSI/MACD/EMA/BB/ATR):
  * Stochastic Oscillator (K/D)
  * Williams %R
  * ADX + DI+/DI- (trend strength)
  * EMA 200 (long-term trend)
  * Ichimoku Tenkan/Kijun + cloud position
  * Classic daily Pivot Points (R1/R2/S1/S2)
  * Swing-based Support / Resistance
  * Fibonacci retracements 38.2 / 50 / 61.8
  * BB width %  (volatility proxy)
  * Aggregated trend / momentum / volatility_regime labels
"""
from __future__ import annotations

import pandas as pd
import ta
from models.schemas import Indicators


def compute_indicators(symbol: str, bars: list[dict]) -> Indicators:
    if len(bars) < 50:
        return Indicators(symbol=symbol, trend="neutral")

    df = pd.DataFrame(bars, columns=["open", "high", "low", "close", "volume"])

    try:
        close = df["close"]
        high = df["high"]
        low = df["low"]
        last_close = float(close.iloc[-1])

        # ── Momentum ────────────────────────────────────────────
        rsi_val = _last(ta.momentum.RSIIndicator(close, window=14).rsi())
        stoch = ta.momentum.StochasticOscillator(high, low, close, window=14, smooth_window=3)
        stoch_k_val = _last(stoch.stoch())
        stoch_d_val = _last(stoch.stoch_signal())
        wr_val = _last(ta.momentum.WilliamsRIndicator(high, low, close, lbp=14).williams_r())

        # ── Trend ──────────────────────────────────────────────
        macd_ind = ta.trend.MACD(close, window_slow=26, window_fast=12, window_sign=9)
        macd_val = _last(macd_ind.macd())
        macd_sig = _last(macd_ind.macd_signal())
        macd_hist = _last(macd_ind.macd_diff())

        ema20_val = _last(ta.trend.EMAIndicator(close, window=20).ema_indicator())
        ema50_val = _last(ta.trend.EMAIndicator(close, window=50).ema_indicator())
        ema200_val = _last(ta.trend.EMAIndicator(close, window=200).ema_indicator()) if len(close) >= 200 else None

        adx_ind = ta.trend.ADXIndicator(high, low, close, window=14)
        adx_val = _last(adx_ind.adx())
        di_plus_val = _last(adx_ind.adx_pos())
        di_minus_val = _last(adx_ind.adx_neg())

        # ── Volatility ─────────────────────────────────────────
        bb = ta.volatility.BollingerBands(close, window=20, window_dev=2)
        bb_upper = _last(bb.bollinger_hband())
        bb_mid = _last(bb.bollinger_mavg())
        bb_lower = _last(bb.bollinger_lband())
        bb_width_pct = None
        if bb_upper and bb_lower and bb_mid:
            bb_width_pct = round((bb_upper - bb_lower) / bb_mid * 100, 4)

        atr_val = _last(
            ta.volatility.AverageTrueRange(high, low, close, window=14).average_true_range()
        )

        # ── Ichimoku (simplified, no future displacement) ──────
        tenkan = _last(((high.rolling(9).max() + low.rolling(9).min()) / 2))
        kijun = _last(((high.rolling(26).max() + low.rolling(26).min()) / 2))
        senkou_a = ((tenkan + kijun) / 2) if (tenkan is not None and kijun is not None) else None
        senkou_b = _last(((high.rolling(52).max() + low.rolling(52).min()) / 2))
        above_cloud = None
        if senkou_a is not None and senkou_b is not None:
            cloud_top = max(senkou_a, senkou_b)
            cloud_bot = min(senkou_a, senkou_b)
            if last_close > cloud_top:
                above_cloud = True
            elif last_close < cloud_bot:
                above_cloud = False
            else:
                above_cloud = None  # inside cloud — ambiguous

        # ── Daily classic pivot (from previous "day" = last 24 bars proxy) ──
        lookback = min(24, len(df) - 1)
        prev_high = float(df["high"].iloc[-lookback - 1:-1].max())
        prev_low = float(df["low"].iloc[-lookback - 1:-1].min())
        prev_close = float(df["close"].iloc[-2])
        pivot = (prev_high + prev_low + prev_close) / 3
        r1 = 2 * pivot - prev_low
        s1 = 2 * pivot - prev_high
        r2 = pivot + (prev_high - prev_low)
        s2 = pivot - (prev_high - prev_low)

        # ── Swing high/low + Fibonacci ─────────────────────────
        swing_window = min(50, len(df))
        swing_high = float(df["high"].iloc[-swing_window:].max())
        swing_low = float(df["low"].iloc[-swing_window:].min())
        diff = swing_high - swing_low
        fib_382 = swing_high - diff * 0.382 if diff > 0 else None
        fib_500 = swing_high - diff * 0.500 if diff > 0 else None
        fib_618 = swing_high - diff * 0.618 if diff > 0 else None

        # ── Aggregated labels ──────────────────────────────────
        trend_label = _determine_trend(
            ema20_val, ema50_val, ema200_val, last_close, adx_val,
            di_plus_val, di_minus_val, above_cloud,
        )
        momentum_label = _determine_momentum(rsi_val, stoch_k_val, macd_hist)
        vol_regime = _determine_volatility(bb_width_pct, atr_val, last_close)

        return Indicators(
            symbol=symbol,
            rsi_14=_r(rsi_val, 2),
            stoch_k=_r(stoch_k_val, 2),
            stoch_d=_r(stoch_d_val, 2),
            williams_r=_r(wr_val, 2),
            macd=_r(macd_val, 6),
            macd_signal=_r(macd_sig, 6),
            macd_hist=_r(macd_hist, 6),
            ema_20=_r(ema20_val, 5),
            ema_50=_r(ema50_val, 5),
            ema_200=_r(ema200_val, 5),
            adx_14=_r(adx_val, 2),
            di_plus=_r(di_plus_val, 2),
            di_minus=_r(di_minus_val, 2),
            bb_upper=_r(bb_upper, 5),
            bb_mid=_r(bb_mid, 5),
            bb_lower=_r(bb_lower, 5),
            bb_width_pct=bb_width_pct,
            atr_14=_r(atr_val, 6),
            ichimoku_tenkan=_r(tenkan, 5),
            ichimoku_kijun=_r(kijun, 5),
            ichimoku_above_cloud=above_cloud,
            pivot=round(pivot, 5),
            pivot_r1=round(r1, 5),
            pivot_s1=round(s1, 5),
            pivot_r2=round(r2, 5),
            pivot_s2=round(s2, 5),
            support=round(swing_low, 5),
            resistance=round(swing_high, 5),
            fib_382=_r(fib_382, 5),
            fib_500=_r(fib_500, 5),
            fib_618=_r(fib_618, 5),
            trend=trend_label,
            momentum=momentum_label,
            volatility_regime=vol_regime,
        )
    except Exception:
        return Indicators(symbol=symbol, trend="neutral")


def _last(series) -> float | None:
    try:
        if series is None:
            return None
        if hasattr(series, "dropna"):
            val = series.dropna().iloc[-1]
        else:
            val = series
        return float(val)
    except Exception:
        return None


def _r(val: float | None, decimals: int) -> float | None:
    return round(val, decimals) if val is not None else None


def _determine_trend(
    ema20, ema50, ema200, close, adx, di_plus, di_minus, above_cloud,
) -> str:
    bullish = 0
    bearish = 0

    if ema20 and ema50:
        if ema20 > ema50 and close > ema20:
            bullish += 2
        elif ema20 < ema50 and close < ema20:
            bearish += 2

    if ema200:
        if close > ema200:
            bullish += 1
        else:
            bearish += 1

    if adx is not None and adx >= 25 and di_plus is not None and di_minus is not None:
        if di_plus > di_minus:
            bullish += 2
        else:
            bearish += 2

    if above_cloud is True:
        bullish += 1
    elif above_cloud is False:
        bearish += 1

    if bullish - bearish >= 2:
        return "bullish"
    if bearish - bullish >= 2:
        return "bearish"
    return "neutral"


def _determine_momentum(rsi, stoch_k, macd_hist) -> str:
    bull = 0
    bear = 0
    if rsi is not None:
        if rsi > 55:
            bull += 1
        elif rsi < 45:
            bear += 1
    if stoch_k is not None:
        if stoch_k > 60:
            bull += 1
        elif stoch_k < 40:
            bear += 1
    if macd_hist is not None:
        if macd_hist > 0:
            bull += 1
        elif macd_hist < 0:
            bear += 1
    if bull - bear >= 1 and bull >= 2:
        return "bullish"
    if bear - bull >= 1 and bear >= 2:
        return "bearish"
    return "neutral"


def _determine_volatility(bb_width_pct, atr, close) -> str:
    # BB width pct heuristics tuned for forex / metals
    if bb_width_pct is None:
        return "normal"
    if bb_width_pct < 0.25:
        return "low"
    if bb_width_pct > 1.20:
        return "high"
    return "normal"


def format_indicators_summary(ind: Indicators) -> str:
    parts = [f"Symbol: {ind.symbol}",
             f"Trend: {ind.trend.upper()}",
             f"Momentum: {ind.momentum.upper()}",
             f"Vol-Regime: {ind.volatility_regime.upper()}"]
    if ind.rsi_14 is not None:
        level = "overbought" if ind.rsi_14 > 70 else "oversold" if ind.rsi_14 < 30 else "neutral"
        parts.append(f"RSI(14): {ind.rsi_14} ({level})")
    if ind.stoch_k is not None and ind.stoch_d is not None:
        parts.append(f"Stoch: K={ind.stoch_k}/D={ind.stoch_d}")
    if ind.adx_14 is not None:
        strength = "strong" if ind.adx_14 >= 25 else "weak"
        parts.append(f"ADX(14): {ind.adx_14} ({strength})")
    if ind.macd_hist is not None:
        direction = "bullish" if ind.macd_hist > 0 else "bearish"
        parts.append(f"MACD-Hist: {ind.macd_hist} ({direction})")
    if ind.ema_20 and ind.ema_50:
        alignment = "bullish" if ind.ema_20 > ind.ema_50 else "bearish"
        parts.append(f"EMA20/50: {ind.ema_20}/{ind.ema_50} ({alignment})")
    if ind.ema_200:
        parts.append(f"EMA200: {ind.ema_200}")
    if ind.ichimoku_above_cloud is True:
        parts.append("Ichimoku: above-cloud")
    elif ind.ichimoku_above_cloud is False:
        parts.append("Ichimoku: below-cloud")
    if ind.pivot:
        parts.append(f"Pivot: {ind.pivot} (R1={ind.pivot_r1}, S1={ind.pivot_s1})")
    if ind.support and ind.resistance:
        parts.append(f"S/R: {ind.support}/{ind.resistance}")
    if ind.atr_14:
        parts.append(f"ATR(14): {ind.atr_14}")
    return " | ".join(parts)
