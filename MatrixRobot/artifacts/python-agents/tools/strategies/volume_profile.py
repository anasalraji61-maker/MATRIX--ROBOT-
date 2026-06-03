"""
Volume Profile (TPO-style approximation when no volume data is available).

Builds a price-distribution histogram over the lookback window:
  • POC — Point of Control (price with the most time/volume)
  • VAH / VAL — Value Area High/Low (70% of activity)
  • HVN / LVN — High/Low Volume Nodes (significant magnets)

Bias inference:
  • Price above VAH → bullish breakout potential / VAH is support
  • Price below VAL → bearish breakdown / VAL is resistance
  • Price within value area → mean-revert toward POC
"""
from __future__ import annotations


def analyze(bars: list[dict], symbol: str = "", bins: int = 40) -> dict:
    if not bars or len(bars) < 30:
        return {"bias": "neutral", "score": 0.0,
                "reasons": ["Insufficient bars"], "key_levels": {}}

    h = [float(b["high"]) for b in bars[-200:]]
    l = [float(b["low"])  for b in bars[-200:]]
    c = [float(b["close"]) for b in bars[-200:]]
    v = [float(b.get("volume", 1) or 1) for b in bars[-200:]]
    last = c[-1]

    hi = max(h); lo = min(l)
    if hi <= lo:
        return {"bias": "neutral", "score": 0.0,
                "reasons": ["Flat range"], "key_levels": {}}
    bin_size = (hi - lo) / bins

    # Distribute each bar's volume across the bins it spans
    histo = [0.0] * bins
    for i, b in enumerate(bars[-200:]):
        bl, bh, bv = float(b["low"]), float(b["high"]), float(b.get("volume", 1) or 1)
        first_bin = max(0, min(bins - 1, int((bl - lo) / bin_size)))
        last_bin  = max(0, min(bins - 1, int((bh - lo) / bin_size)))
        if first_bin == last_bin:
            histo[first_bin] += bv
        else:
            share = bv / max(1, (last_bin - first_bin + 1))
            for k in range(first_bin, last_bin + 1):
                histo[k] += share

    poc_idx = max(range(bins), key=lambda i: histo[i])
    poc_price = lo + (poc_idx + 0.5) * bin_size

    # Value Area: expand around POC until 70% of volume is captured
    total = sum(histo)
    target = total * 0.70
    captured = histo[poc_idx]
    lo_idx = hi_idx = poc_idx
    while captured < target and (lo_idx > 0 or hi_idx < bins - 1):
        next_lo = histo[lo_idx - 1] if lo_idx > 0 else -1
        next_hi = histo[hi_idx + 1] if hi_idx < bins - 1 else -1
        if next_hi >= next_lo:
            hi_idx += 1; captured += next_hi
        else:
            lo_idx -= 1; captured += next_lo
    val_price = lo + (lo_idx + 0.0) * bin_size
    vah_price = lo + (hi_idx + 1.0) * bin_size

    # Identify HVN/LVN (top/bottom 20% of bin values, excluding POC)
    sorted_bins = sorted(enumerate(histo), key=lambda x: x[1], reverse=True)
    hvn_prices = [round(lo + (i + 0.5) * bin_size, 5) for i, _ in sorted_bins[1:4]]
    lvn_prices = [round(lo + (i + 0.5) * bin_size, 5) for i, _ in sorted(enumerate(histo), key=lambda x: x[1])[:3]]

    reasons: list[str] = []
    bias = "neutral"; score = 0.0

    if last > vah_price:
        # Above value — bullish acceptance OR exhaustion if too far
        excess = (last - vah_price) / max(vah_price - val_price, bin_size)
        if excess < 0.5:
            bias = "bullish"; score = 0.45
            reasons.append(f"Price above VAH {vah_price:.5f} — bullish acceptance")
        else:
            bias = "bearish"; score = -0.25
            reasons.append(f"Price extended {excess:.1f}× value range above VAH — mean revert risk")
    elif last < val_price:
        excess = (val_price - last) / max(vah_price - val_price, bin_size)
        if excess < 0.5:
            bias = "bearish"; score = -0.45
            reasons.append(f"Price below VAL {val_price:.5f} — bearish acceptance")
        else:
            bias = "bullish"; score = 0.25
            reasons.append(f"Price extended {excess:.1f}× value range below VAL — mean revert risk")
    else:
        # Within value area — bias toward POC
        if last < poc_price:
            bias = "bullish"; score = 0.20
            reasons.append(f"Inside value area, below POC {poc_price:.5f} — mean revert UP")
        elif last > poc_price:
            bias = "bearish"; score = -0.20
            reasons.append(f"Inside value area, above POC {poc_price:.5f} — mean revert DOWN")

    return {
        "bias": bias,
        "score": round(score, 3),
        "reasons": reasons,
        "key_levels": {
            "POC": round(poc_price, 5),
            "VAH": round(vah_price, 5),
            "VAL": round(val_price, 5),
            "HVN": hvn_prices,
            "LVN": lvn_prices,
            "range_high": round(hi, 5),
            "range_low":  round(lo, 5),
        },
    }
