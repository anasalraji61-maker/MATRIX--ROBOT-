"""Feature vector from indicator + ICT snapshots at trade entry."""
from __future__ import annotations

from typing import Any

FEATURE_NAMES: tuple[str, ...] = (
    "side",              # BUY=1, SELL=-1
    "norm_score",        # ensemble score at entry [-1, 1]
    "rsi_norm",          # (rsi-50)/50
    "stoch_k_norm",      # (k-50)/50
    "macd_hist_sign",    # tanh-scaled macd hist vs price
    "ema_stack",         # +1 if ema20>ema50, -1 if reverse, 0 else
    "ema200_bias",       # +1 if mid>ema200, -1 if reverse, 0 else
    "adx_norm",          # adx/100
    "di_spread",         # (di+ - di-) / 100
    "bb_width_pct",
    "atr_pct",           # atr/price * 10000
    "ict_score",
    "ichimoku_cloud",    # +1 above, -1 below, 0 unknown
    "williams_norm",     # (wr+50)/50  wr is -100..0
)


def _f(val: Any, default: float = 0.0) -> float:
    if val is None:
        return default
    try:
        return float(val)
    except (TypeError, ValueError):
        return default


def extract_features(
    ind: dict,
    ict: dict,
    norm_score: float,
    side: str,
    price: float,
) -> list[float]:
    """Return fixed-length feature vector for one entry bar."""
    price = max(price, 1e-9)
    rsi = _f(ind.get("rsi_14"), 50.0)
    stoch_k = _f(ind.get("stoch_k"), 50.0)
    mh = _f(ind.get("macd_hist"))
    e20, e50, e200 = ind.get("ema_20"), ind.get("ema_50"), ind.get("ema_200")
    mid = ind.get("bb_mid")
    adx = _f(ind.get("adx_14"))
    dip, dim = _f(ind.get("di_plus")), _f(ind.get("di_minus"))
    bb_w = _f(ind.get("bb_width_pct"))
    atr = _f(ind.get("atr_14"))
    wr = _f(ind.get("williams_r"), -50.0)
    ict_score = _f((ict or {}).get("score"))

    ema_stack = 0.0
    if e20 is not None and e50 is not None:
        ema_stack = 1.0 if float(e20) > float(e50) else (-1.0 if float(e20) < float(e50) else 0.0)

    ema200_bias = 0.0
    if e200 is not None and mid is not None:
        ema200_bias = 1.0 if float(mid) > float(e200) else (-1.0 if float(mid) < float(e200) else 0.0)

    ich = ind.get("ichimoku_above_cloud")
    ich_cloud = 0.0
    if ich is True:
        ich_cloud = 1.0
    elif ich is False:
        ich_cloud = -1.0

    side_val = 1.0 if side.upper() == "BUY" else -1.0
    macd_hist_sign = max(-1.0, min(1.0, (mh / price) * 5000.0))

    return [
        side_val,
        max(-1.0, min(1.0, float(norm_score))),
        (rsi - 50.0) / 50.0,
        (stoch_k - 50.0) / 50.0,
        macd_hist_sign,
        ema_stack,
        ema200_bias,
        adx / 100.0,
        (dip - dim) / 100.0,
        bb_w / 100.0 if bb_w else 0.0,
        (atr / price) * 10000.0,
        max(-1.0, min(1.0, ict_score)),
        ich_cloud,
        (wr + 50.0) / 50.0,
    ]


def feature_dim() -> int:
    return len(FEATURE_NAMES)
