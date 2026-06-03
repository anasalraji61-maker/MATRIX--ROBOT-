"""
Elliott Wave counter — simplified 5-impulse + 3-correction detector.

Walks ZigZag-style swings (filtered by ATR%) and labels:
  IMPULSE_UP / IMPULSE_DOWN  — series of higher-highs/lows or LH/LL
  CORRECTION_UP / CORRECTION_DOWN — 3-leg counter move
  UNCLEAR

Returns wave count (estimated current wave 1-5 or A-C), bias, and the next
expected move per Elliott rules.
"""
from __future__ import annotations


def _zigzag(h: list[float], l: list[float], threshold_pct: float = 0.3) -> list[dict]:
    """ATR%-style zigzag. Returns list of pivots [{i, price, kind}]."""
    if not h or not l:
        return []
    pivots: list[dict] = []
    direction = 0  # +1 up, -1 down
    last_high_i, last_high_p = 0, h[0]
    last_low_i,  last_low_p  = 0, l[0]
    thresh = threshold_pct / 100.0

    for i in range(1, len(h)):
        # Check for new highs/lows in active direction
        if h[i] > last_high_p:
            last_high_i, last_high_p = i, h[i]
        if l[i] < last_low_p:
            last_low_i, last_low_p = i, l[i]

        if direction >= 0:
            # Look for reversal down
            if last_high_p > 0 and (last_high_p - l[i]) / last_high_p >= thresh:
                pivots.append({"i": last_high_i, "price": last_high_p, "kind": "high"})
                direction = -1
                last_low_i, last_low_p = i, l[i]
        if direction <= 0:
            # Look for reversal up
            if last_low_p > 0 and (h[i] - last_low_p) / last_low_p >= thresh:
                pivots.append({"i": last_low_i, "price": last_low_p, "kind": "low"})
                direction = +1
                last_high_i, last_high_p = i, h[i]

    return pivots


def analyze(bars: list[dict], symbol: str = "") -> dict:
    if not bars or len(bars) < 50:
        return {"bias": "neutral", "score": 0.0, "wave_count": 0,
                "current_wave": "?", "reasons": ["Insufficient bars"], "key_levels": {}}

    h = [float(b["high"]) for b in bars]
    l = [float(b["low"])  for b in bars]
    c = [float(b["close"]) for b in bars]
    last = c[-1]

    # Use a 0.3% pivot threshold (suits forex H1; falls back gracefully)
    pivots = _zigzag(h, l, threshold_pct=0.3)
    if len(pivots) < 4:
        return {"bias": "neutral", "score": 0.0, "wave_count": len(pivots),
                "current_wave": "?", "reasons": [f"Only {len(pivots)} pivots found"],
                "key_levels": {}}

    # Take last 7 pivots — enough for a full 5+3 sequence
    recent = pivots[-7:]
    prices = [p["price"] for p in recent]
    kinds  = [p["kind"] for p in recent]

    reasons: list[str] = []
    bias = "neutral"; score = 0.0; current_wave = "?"; expected_next = "?"

    # Impulse up: alternating L,H,L,H,L pattern with each H>prevH and each L>prevL
    if len(recent) >= 5:
        highs = [p for p in recent if p["kind"] == "high"]
        lows  = [p for p in recent if p["kind"] == "low"]

        impulse_up = (len(highs) >= 2 and len(lows) >= 2
                      and all(highs[i]["price"] > highs[i-1]["price"] for i in range(1, len(highs)))
                      and all(lows[i]["price"]  > lows[i-1]["price"]  for i in range(1, len(lows))))
        impulse_down = (len(highs) >= 2 and len(lows) >= 2
                        and all(highs[i]["price"] < highs[i-1]["price"] for i in range(1, len(highs)))
                        and all(lows[i]["price"]  < lows[i-1]["price"]  for i in range(1, len(lows))))

        if impulse_up:
            # Count waves since last clean low
            wave_count = len(highs) + len(lows)
            last_kind = recent[-1]["kind"]
            # Wave 3 is the strongest (longest); wave 5 often shows divergence
            if wave_count <= 2:
                current_wave = "1"; expected_next = "2 (pullback)"
                bias = "bullish"; score = 0.4
            elif wave_count == 3:
                current_wave = "3" if last_kind == "high" else "2"
                bias = "bullish"; score = 0.55
                expected_next = "4 (pullback)" if current_wave == "3" else "3 (impulse)"
            elif wave_count == 4:
                current_wave = "4"; expected_next = "5 (final impulse)"
                bias = "bullish"; score = 0.35
            else:
                current_wave = "5"; expected_next = "ABC correction"
                bias = "bullish"; score = 0.15
                reasons.append("Wave 5 — late in impulse, reduce conviction")
            reasons.append(f"Impulse UP detected ({wave_count} legs)")

        elif impulse_down:
            wave_count = len(highs) + len(lows)
            last_kind = recent[-1]["kind"]
            if wave_count <= 2:
                current_wave = "1"; expected_next = "2 (bounce)"
                bias = "bearish"; score = -0.4
            elif wave_count == 3:
                current_wave = "3" if last_kind == "low" else "2"
                bias = "bearish"; score = -0.55
                expected_next = "4 (bounce)" if current_wave == "3" else "3 (impulse)"
            elif wave_count == 4:
                current_wave = "4"; expected_next = "5 (final impulse)"
                bias = "bearish"; score = -0.35
            else:
                current_wave = "5"; expected_next = "ABC bounce"
                bias = "bearish"; score = -0.15
                reasons.append("Wave 5 — late in impulse, reduce conviction")
            reasons.append(f"Impulse DOWN detected ({wave_count} legs)")
        else:
            current_wave = "corrective"
            reasons.append("No clean impulse — likely corrective/ABC")

    return {
        "bias": bias,
        "score": round(score, 3),
        "wave_count": len(pivots),
        "current_wave": current_wave,
        "expected_next": expected_next,
        "reasons": reasons,
        "key_levels": {
            "last_pivot_price": round(prices[-1], 5),
            "last_pivot_kind": kinds[-1],
            "swing_high": round(max(prices), 5),
            "swing_low":  round(min(prices), 5),
        },
    }
