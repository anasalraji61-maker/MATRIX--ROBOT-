"""
Wyckoff phase detector — lightweight rule-based approximation.

Identifies one of: ACCUMULATION, MARKUP, DISTRIBUTION, MARKDOWN, NEUTRAL
based on price range contraction, volume behaviour (proxied by ATR if no
volume), and position vs prior trading range.

Phases:
  • ACCUMULATION: sideways after downtrend, contracting range, springs
  • MARKUP:       breakout above range with expanding momentum
  • DISTRIBUTION: sideways after uptrend, contracting range, upthrusts
  • MARKDOWN:     breakdown below range with expanding momentum
"""
from __future__ import annotations
from statistics import mean, pstdev


def _to_lists(bars):
    o = [float(b["open"]) for b in bars]
    h = [float(b["high"]) for b in bars]
    l = [float(b["low"])  for b in bars]
    c = [float(b["close"]) for b in bars]
    v = [float(b.get("volume", 0) or 0) for b in bars]
    return o, h, l, c, v


def analyze(bars: list[dict], symbol: str = "") -> dict:
    if not bars or len(bars) < 50:
        return {"bias": "neutral", "score": 0.0, "phase": "UNKNOWN",
                "reasons": ["Insufficient bars for Wyckoff"], "key_levels": {}}

    o, h, l, c, v = _to_lists(bars)
    n = len(c)
    last = c[-1]

    # Trading range: last 30 bars vs prior 30 bars
    recent_h = max(h[-30:]); recent_l = min(l[-30:])
    prior_h  = max(h[-60:-30]); prior_l = min(l[-60:-30])
    recent_range = recent_h - recent_l
    prior_range  = prior_h  - prior_l
    contraction  = (recent_range / prior_range) if prior_range > 0 else 1.0

    # Trend before the range (use first 30 vs middle 30)
    pre_mean  = mean(c[-90:-60]) if n >= 90 else mean(c[:30])
    mid_mean  = mean(c[-60:-30])
    cur_mean  = mean(c[-30:])
    pre_trend = "down" if mid_mean < pre_mean * 0.995 else ("up" if mid_mean > pre_mean * 1.005 else "flat")

    # Breakout state vs recent range
    above = last > recent_h * 0.999
    below = last < recent_l * 1.001

    # Volatility expansion (markup/markdown) vs contraction (acc/dist)
    last20_std = pstdev(c[-20:])
    prev20_std = pstdev(c[-40:-20])
    vol_expanding = last20_std > prev20_std * 1.15
    vol_contracting = last20_std < prev20_std * 0.85

    phase = "NEUTRAL"; bias = "neutral"; score = 0.0
    reasons: list[str] = []

    if above and vol_expanding and pre_trend != "down":
        phase = "MARKUP"; bias = "bullish"; score = 0.55
        reasons.append(f"Breakout above {recent_h:.5f} with expanding vol")
    elif below and vol_expanding and pre_trend != "up":
        phase = "MARKDOWN"; bias = "bearish"; score = -0.55
        reasons.append(f"Breakdown below {recent_l:.5f} with expanding vol")
    elif pre_trend == "down" and contraction < 0.85 and vol_contracting:
        phase = "ACCUMULATION"; bias = "bullish"; score = 0.30
        reasons.append("Range contraction after downtrend — accumulation")
        # Spring: brief penetration of recent low then recovery
        if min(l[-10:]) < recent_l * 1.0005 and last > recent_l:
            score += 0.20; reasons.append("Spring detected (false breakdown reclaimed)")
    elif pre_trend == "up" and contraction < 0.85 and vol_contracting:
        phase = "DISTRIBUTION"; bias = "bearish"; score = -0.30
        reasons.append("Range contraction after uptrend — distribution")
        # Upthrust: brief penetration of recent high then failure
        if max(h[-10:]) > recent_h * 0.9995 and last < recent_h:
            score -= 0.20; reasons.append("Upthrust detected (false breakout failed)")
    else:
        reasons.append(f"No clear Wyckoff phase (contraction={contraction:.2f}, pre_trend={pre_trend})")

    return {
        "bias": bias,
        "score": round(max(-1.0, min(1.0, score)), 3),
        "phase": phase,
        "reasons": reasons,
        "key_levels": {
            "range_high": round(recent_h, 5),
            "range_low":  round(recent_l, 5),
            "contraction_ratio": round(contraction, 3),
        },
    }
