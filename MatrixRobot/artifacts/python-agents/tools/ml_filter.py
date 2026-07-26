"""Supervisor ML gate — scores approved trades with trained signal model (NumPy)."""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from backtest.engine import _score_bar
from ml.features import extract_features
from ml.inference import NumpySignalModel
from models.schemas import ApprovedTrade

logger = logging.getLogger("matrix.ml_filter")

_model: NumpySignalModel | None = None
_model_path: str | None = None
_load_error: str | None = None


def _resolve_json_path(settings) -> Path | None:
    explicit = (settings.ml_model_json_path or "").strip()
    if explicit:
        p = Path(explicit)
        if p.is_file():
            return p
    pt = Path(settings.ml_model_path or "")
    if pt.is_file():
        sibling = pt.with_suffix(".json")
        if sibling.is_file():
            return sibling
    default = Path("ml_models/signal_EURUSD_XAUUSD_2000bars.json")
    if default.is_file():
        return default
    return None


def _load_model(settings) -> NumpySignalModel | None:
    global _model, _model_path, _load_error
    if not settings.ml_filter_enabled:
        return None

    json_path = _resolve_json_path(settings)
    if json_path is None:
        _load_error = "ML model JSON not found — run scripts/export_ml_model.py on VPS"
        logger.warning(_load_error)
        return None

    path_str = str(json_path.resolve())
    if _model is not None and _model_path == path_str:
        return _model

    try:
        _model = NumpySignalModel.load(json_path)
        _model_path = path_str
        _load_error = None
        logger.info("ML filter loaded: %s", path_str)
        return _model
    except Exception as e:
        _load_error = f"{type(e).__name__}: {e}"
        logger.warning("ML filter load failed: %s", _load_error)
        _model = None
        _model_path = None
        return None


def score_trade(
    trade: ApprovedTrade,
    state: dict,
    settings,
) -> dict[str, Any]:
    """Return win probability + features for one candidate trade."""
    indicators = state.get("indicators") or {}
    ict_map = state.get("ict") or {}
    ind = indicators.get(trade.symbol.upper()) or indicators.get(trade.symbol) or {}
    ict = ict_map.get(trade.symbol.upper()) or ict_map.get(trade.symbol) or {}

    norm = _score_bar(ind, ict)
    price = float(ind.get("bb_mid") or ind.get("ema_20") or 0.0)
    if price <= 0:
        quotes = state.get("quotes") or {}
        q = quotes.get(trade.symbol.upper()) or quotes.get(trade.symbol) or {}
        price = float(q.get("mid") or q.get("close") or 0.0)

    feats = extract_features(ind, ict, norm, trade.signal, max(price, 1e-9))
    model = _load_model(settings)
    if model is None:
        return {
            "symbol": trade.symbol,
            "signal": trade.signal,
            "win_prob": None,
            "norm_score": round(norm, 4),
            "loaded": False,
            "error": _load_error,
        }

    prob = model.predict_proba(feats)
    return {
        "symbol": trade.symbol,
        "signal": trade.signal,
        "win_prob": round(prob, 4),
        "norm_score": round(norm, 4),
        "strength": trade.strength,
        "loaded": True,
    }


def filter_trades(
    approved: list[ApprovedTrade],
    state: dict,
    settings,
) -> tuple[list[ApprovedTrade], list[dict[str, Any]]]:
    """Filter supervisor batch. Shadow mode logs only; enforce mode blocks weak signals."""
    if not approved or not settings.ml_filter_enabled:
        return approved, []

    model = _load_model(settings)
    scores: list[dict[str, Any]] = []
    kept: list[ApprovedTrade] = []
    threshold = float(settings.ml_min_win_prob)
    mode = (settings.ml_filter_mode or "shadow").lower()

    for trade in approved:
        s = score_trade(trade, state, settings)
        scores.append(s)
        prob = s.get("win_prob")
        if prob is None:
            kept.append(trade)
            continue
        if prob >= threshold:
            kept.append(trade)
        else:
            logger.info(
                "ML filter blocked %s %s — win_prob=%.3f < %.3f (mode=%s)",
                trade.symbol, trade.signal, prob, threshold, mode,
            )

    if mode in ("shadow", "advisory"):
        if mode == "advisory":
            for s in scores:
                prob = s.get("win_prob")
                if prob is not None and prob < threshold:
                    logger.warning(
                        "ML advisory would block %s — win_prob=%.3f < %.3f (not enforced)",
                        s.get("symbol"), prob, threshold,
                    )
        return approved, scores

    return kept, scores


def get_status(settings=None) -> dict[str, Any]:
    from config import get_settings

    s = settings or get_settings()
    json_path = _resolve_json_path(s)
    model = _load_model(s) if s.ml_filter_enabled else None
    return {
        "enabled": s.ml_filter_enabled,
        "mode": s.ml_filter_mode,
        "min_win_prob": s.ml_min_win_prob,
        "model_json": str(json_path) if json_path else None,
        "model_loaded": model is not None,
        "load_error": _load_error,
        "pytorch_required": False,
        "note": "Brain uses NumPy JSON weights — no torch in .venv needed",
    }
