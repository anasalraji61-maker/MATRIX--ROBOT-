"""
Harmonic pattern detector — Gartley, Bat, Butterfly, Crab, Cypher, Shark.

Works on 4 most recent ZigZag pivots (X, A, B, C, D candidates) and checks
Fibonacci retracement ratios against each pattern's known signature within
±5% tolerance. Emits the most-likely completed pattern and PRZ
(Potential Reversal Zone) as the entry guidance for the LLM.
"""
from __future__ import annotations
from .elliott import _zigzag


# Pattern signatures: AB/XA, BC/AB, CD/BC, AD/XA, direction sign
PATTERNS = [
    {"name": "Gartley",   "ab_xa": 0.618, "bc_ab": (0.382, 0.886), "cd_bc": (1.272, 1.618), "ad_xa": 0.786},
    {"name": "Bat",       "ab_xa": (0.382, 0.500), "bc_ab": (0.382, 0.886), "cd_bc": (1.618, 2.618), "ad_xa": 0.886},
    {"name": "Butterfly", "ab_xa": 0.786, "bc_ab": (0.382, 0.886), "cd_bc": (1.618, 2.618), "ad_xa": 1.270},
    {"name": "Crab",      "ab_xa": (0.382, 0.618), "bc_ab": (0.382, 0.886), "cd_bc": (2.240, 3.618), "ad_xa": 1.618},
    {"name": "Cypher",    "ab_xa": (0.382, 0.618), "bc_ab": (1.130, 1.414), "cd_bc": (1.272, 2.000), "ad_xa": 0.786},
    {"name": "Shark",     "ab_xa": (0.382, 0.618), "bc_ab": (1.130, 1.618), "cd_bc": (1.618, 2.240), "ad_xa": 0.886},
]

TOLERANCE = 0.07  # ±7% on each ratio


def _ratio(num: float, den: float) -> float:
    return abs(num / den) if den != 0 else 0.0


def _matches(actual: float, target) -> bool:
    if isinstance(target, tuple):
        lo, hi = target
        return lo * (1 - TOLERANCE) <= actual <= hi * (1 + TOLERANCE)
    return target * (1 - TOLERANCE) <= actual <= target * (1 + TOLERANCE)


def analyze(bars: list[dict], symbol: str = "") -> dict:
    if not bars or len(bars) < 60:
        return {"bias": "neutral", "score": 0.0, "pattern": "none",
                "reasons": ["Insufficient bars"], "key_levels": {}}

    h = [float(b["high"]) for b in bars]
    l = [float(b["low"])  for b in bars]
    pivots = _zigzag(h, l, threshold_pct=0.3)
    if len(pivots) < 5:
        return {"bias": "neutral", "score": 0.0, "pattern": "none",
                "reasons": [f"Only {len(pivots)} pivots"], "key_levels": {}}

    X, A, B, C, D = pivots[-5:]
    if not (X["kind"] != A["kind"] != B["kind"] != C["kind"] != D["kind"]):
        return {"bias": "neutral", "score": 0.0, "pattern": "incomplete",
                "reasons": ["Pivots don't alternate cleanly"], "key_levels": {}}

    xa = abs(A["price"] - X["price"])
    ab = abs(B["price"] - A["price"])
    bc = abs(C["price"] - B["price"])
    cd = abs(D["price"] - C["price"])
    ad = abs(D["price"] - A["price"])
    if xa == 0:
        return {"bias": "neutral", "score": 0.0, "pattern": "none",
                "reasons": ["XA leg has zero range"], "key_levels": {}}

    ab_xa = _ratio(ab, xa)
    bc_ab = _ratio(bc, ab)
    cd_bc = _ratio(cd, bc)
    ad_xa = _ratio(ad, xa)

    # Direction: bullish patterns end at a LOW (D=low), bearish at HIGH
    bullish = D["kind"] == "low"
    direction = "bullish" if bullish else "bearish"

    best_match = None
    best_score = 0
    for pat in PATTERNS:
        matches = sum([
            _matches(ab_xa, pat["ab_xa"]),
            _matches(bc_ab, pat["bc_ab"]),
            _matches(cd_bc, pat["cd_bc"]),
            _matches(ad_xa, pat["ad_xa"]),
        ])
        if matches > best_score:
            best_score = matches
            best_match = pat

    if best_match is None or best_score < 3:
        return {
            "bias": "neutral", "score": 0.0, "pattern": "no_match",
            "reasons": [f"Best fit only {best_score}/4 ratios"],
            "key_levels": {"X": X["price"], "A": A["price"], "B": B["price"],
                           "C": C["price"], "D": D["price"]},
        }

    # PRZ = D ± a small zone (use 0.382× AB as half-width estimate)
    prz_half = ab * 0.20
    prz_low  = round(D["price"] - prz_half, 5)
    prz_high = round(D["price"] + prz_half, 5)

    score = (0.45 if best_score == 3 else 0.65) * (1 if bullish else -1)

    return {
        "bias": direction,
        "score": round(score, 3),
        "pattern": best_match["name"],
        "match_quality": best_score,
        "reasons": [
            f"{best_match['name']} {direction} pattern — {best_score}/4 ratios match",
            f"AB/XA={ab_xa:.3f}, BC/AB={bc_ab:.3f}, CD/BC={cd_bc:.3f}, AD/XA={ad_xa:.3f}",
            f"PRZ entry zone: {prz_low}–{prz_high}",
        ],
        "key_levels": {
            "X": round(X["price"], 5), "A": round(A["price"], 5),
            "B": round(B["price"], 5), "C": round(C["price"], 5),
            "D": round(D["price"], 5),
            "prz_low": prz_low, "prz_high": prz_high,
        },
    }
