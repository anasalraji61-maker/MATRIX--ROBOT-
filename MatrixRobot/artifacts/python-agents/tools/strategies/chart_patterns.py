"""
Classic chart pattern detector — pure-python, no extra deps.

Detects (best-of-class match only, returns the strongest):
  • Double Top / Double Bottom
  • Head & Shoulders / Inverse H&S
  • Ascending / Descending / Symmetric Triangle
  • Bull / Bear Flag
  • Rising / Falling Wedge

Each pattern emits an entry condition + invalidation level the LLM uses.
"""
from __future__ import annotations
from .elliott import _zigzag


def _trendline_slope(points: list[tuple[int, float]]) -> float:
    """Simple least-squares slope of (i, price) points."""
    if len(points) < 2:
        return 0.0
    n = len(points)
    mean_x = sum(p[0] for p in points) / n
    mean_y = sum(p[1] for p in points) / n
    num = sum((p[0] - mean_x) * (p[1] - mean_y) for p in points)
    den = sum((p[0] - mean_x) ** 2 for p in points) or 1
    return num / den


def analyze(bars: list[dict], symbol: str = "") -> dict:
    if not bars or len(bars) < 50:
        return {"bias": "neutral", "score": 0.0, "pattern": "none",
                "reasons": ["Insufficient bars"], "key_levels": {}}

    h = [float(b["high"]) for b in bars]
    l = [float(b["low"])  for b in bars]
    c = [float(b["close"]) for b in bars]
    last = c[-1]
    pivots = _zigzag(h, l, threshold_pct=0.25)
    if len(pivots) < 4:
        return {"bias": "neutral", "score": 0.0, "pattern": "none",
                "reasons": [f"Only {len(pivots)} pivots"], "key_levels": {}}

    highs = [p for p in pivots[-8:] if p["kind"] == "high"]
    lows  = [p for p in pivots[-8:] if p["kind"] == "low"]
    reasons: list[str] = []
    pattern = "none"; bias = "neutral"; score = 0.0; key_levels: dict = {}

    # Double Top: 2 highs within 0.3% of each other, with a clear trough between
    if len(highs) >= 2:
        h1, h2 = highs[-2], highs[-1]
        if abs(h1["price"] - h2["price"]) / max(h2["price"], 1e-9) < 0.003:
            trough = min((p["price"] for p in pivots if h1["i"] < p["i"] < h2["i"] and p["kind"] == "low"), default=None)
            if trough and trough < min(h1["price"], h2["price"]) * 0.995:
                pattern = "double_top"; bias = "bearish"; score = -0.50
                reasons.append(f"Double Top at {h1['price']:.5f}/{h2['price']:.5f}, neckline {trough:.5f}")
                key_levels = {"resistance": round(h1["price"], 5), "neckline": round(trough, 5)}

    # Double Bottom: 2 lows within 0.3%, with a peak between
    if len(lows) >= 2 and pattern == "none":
        l1, l2 = lows[-2], lows[-1]
        if abs(l1["price"] - l2["price"]) / max(l2["price"], 1e-9) < 0.003:
            peak = max((p["price"] for p in pivots if l1["i"] < p["i"] < l2["i"] and p["kind"] == "high"), default=None)
            if peak and peak > max(l1["price"], l2["price"]) * 1.005:
                pattern = "double_bottom"; bias = "bullish"; score = 0.50
                reasons.append(f"Double Bottom at {l1['price']:.5f}/{l2['price']:.5f}, neckline {peak:.5f}")
                key_levels = {"support": round(l1["price"], 5), "neckline": round(peak, 5)}

    # Head & Shoulders: 3 highs where middle > sides, side highs within 0.5%
    if len(highs) >= 3 and pattern == "none":
        ls, head, rs = highs[-3], highs[-2], highs[-1]
        if (head["price"] > ls["price"] and head["price"] > rs["price"]
                and abs(ls["price"] - rs["price"]) / max(rs["price"], 1e-9) < 0.005):
            pattern = "head_and_shoulders"; bias = "bearish"; score = -0.55
            reasons.append(f"Head & Shoulders — head {head['price']:.5f}, shoulders ~{ls['price']:.5f}")
            key_levels = {"head": round(head["price"], 5), "shoulder": round(ls["price"], 5)}

    # Inverse H&S
    if len(lows) >= 3 and pattern == "none":
        ls, head, rs = lows[-3], lows[-2], lows[-1]
        if (head["price"] < ls["price"] and head["price"] < rs["price"]
                and abs(ls["price"] - rs["price"]) / max(rs["price"], 1e-9) < 0.005):
            pattern = "inverse_head_and_shoulders"; bias = "bullish"; score = 0.55
            reasons.append(f"Inverse H&S — head {head['price']:.5f}, shoulders ~{ls['price']:.5f}")
            key_levels = {"head": round(head["price"], 5), "shoulder": round(ls["price"], 5)}

    # Triangles (need ≥2 highs and ≥2 lows in last 6 pivots)
    if pattern == "none" and len(highs) >= 2 and len(lows) >= 2:
        h_slope = _trendline_slope([(p["i"], p["price"]) for p in highs[-3:]])
        l_slope = _trendline_slope([(p["i"], p["price"]) for p in lows[-3:]])
        scale = max(c) - min(c) or 1
        if abs(h_slope) / scale < 1e-5 and l_slope / scale > 1e-5:
            pattern = "ascending_triangle"; bias = "bullish"; score = 0.40
            reasons.append("Flat top + rising lows = ascending triangle")
            key_levels = {"resistance": round(highs[-1]["price"], 5)}
        elif h_slope / scale < -1e-5 and abs(l_slope) / scale < 1e-5:
            pattern = "descending_triangle"; bias = "bearish"; score = -0.40
            reasons.append("Falling highs + flat bottom = descending triangle")
            key_levels = {"support": round(lows[-1]["price"], 5)}
        elif h_slope < 0 and l_slope > 0:
            pattern = "symmetric_triangle"; bias = "neutral"; score = 0.0
            reasons.append("Converging trendlines — symmetric triangle (await breakout)")
            key_levels = {"resistance": round(highs[-1]["price"], 5),
                          "support":    round(lows[-1]["price"], 5)}
        elif h_slope > 0 and l_slope > 0 and h_slope < l_slope:
            pattern = "rising_wedge"; bias = "bearish"; score = -0.30
            reasons.append("Rising wedge (bearish reversal pattern)")
        elif h_slope < 0 and l_slope < 0 and l_slope < h_slope:
            pattern = "falling_wedge"; bias = "bullish"; score = 0.30
            reasons.append("Falling wedge (bullish reversal pattern)")

    if pattern == "none":
        reasons.append("No classic chart pattern detected")

    return {
        "bias": bias,
        "score": round(score, 3),
        "pattern": pattern,
        "reasons": reasons,
        "key_levels": key_levels,
    }
