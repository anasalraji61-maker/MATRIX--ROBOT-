"""Background PyTorch + MLflow retrain scheduler."""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone

logger = logging.getLogger("matrix.ml_retrain")

_task: asyncio.Task | None = None
_last_run: str | None = None
_last_result: dict | None = None
_running = False


async def _build_combined_dataset(symbols: list[str], bars: int):
    from ml.dataset import build_from_backtest, _samples_to_arrays

    all_samples = []
    for sym in symbols:
        ds = await build_from_backtest(sym, bars_limit=bars, timeframe="H1")
        all_samples.extend(ds.samples)
    if not all_samples:
        return None
    return _samples_to_arrays(all_samples)


async def _train_async(settings) -> dict:
    symbols = [
        s.strip().upper()
        for s in (settings.ml_retrain_symbols or "EURUSD,XAUUSD").split(",")
        if s.strip()
    ]
    bars = int(getattr(settings, "ml_retrain_bars", 3000))
    from ml.trainer import _require_ml_deps, train_classifier, default_mlflow_uri

    _require_ml_deps()
    dataset = await _build_combined_dataset(symbols, bars)
    if dataset is None or dataset.n_samples < 30:
        return {
            "ok": False,
            "reason": f"insufficient samples ({getattr(dataset, 'n_samples', 0)})",
        }
    return train_classifier(
        dataset,
        symbols=symbols,
        bars=bars,
        mlflow_uri=default_mlflow_uri(),
        run_name=f"auto_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M')}",
    )


def _run_retrain_sync(settings) -> dict:
    return asyncio.run(_train_async(settings))


async def run_retrain_once() -> dict:
    global _last_run, _last_result, _running
    from config import get_settings

    s = get_settings()
    if not getattr(s, "ml_retrain_enabled", False):
        return {"ok": False, "reason": "ml_retrain_disabled"}

    if _running:
        return {"ok": False, "reason": "retrain_already_running"}

    _running = True
    try:
        logger.info("ML auto-retrain starting — symbols=%s", s.ml_retrain_symbols)
        result = await asyncio.to_thread(_run_retrain_sync, s)
        _last_run = datetime.now(timezone.utc).isoformat()
        _last_result = result
        if result.get("ok"):
            logger.info(
                "ML auto-retrain OK — json=%s run=%s",
                result.get("model_json"),
                result.get("run_id"),
            )
            from tools import ml_filter
            ml_filter._model = None
            ml_filter._model_path = None
        else:
            logger.warning("ML auto-retrain skipped/failed: %s", result.get("reason"))
        return result
    except Exception as e:
        _last_result = {"ok": False, "error": str(e)}
        logger.error("ML auto-retrain error: %s", e)
        return _last_result
    finally:
        _running = False


async def _loop():
    from config import get_settings

    while True:
        s = get_settings()
        hours = max(1, int(getattr(s, "ml_retrain_interval_hours", 168)))
        await asyncio.sleep(hours * 3600)
        if getattr(s, "ml_retrain_enabled", False):
            await run_retrain_once()


def start_background() -> None:
    global _task
    from config import get_settings

    s = get_settings()
    if not getattr(s, "ml_retrain_enabled", False):
        logger.info("ML auto-retrain disabled")
        return
    if _task and not _task.done():
        return
    _task = asyncio.create_task(_loop())
    logger.info(
        "ML auto-retrain scheduler started — every %sh (PyTorch + MLflow)",
        s.ml_retrain_interval_hours,
    )


async def stop_background() -> None:
    global _task
    if _task and not _task.done():
        _task.cancel()
        try:
            await _task
        except asyncio.CancelledError:
            pass
    _task = None


def get_status() -> dict:
    from config import get_settings

    s = get_settings()
    return {
        "enabled": getattr(s, "ml_retrain_enabled", False),
        "interval_hours": getattr(s, "ml_retrain_interval_hours", 168),
        "symbols": s.ml_retrain_symbols,
        "bars": getattr(s, "ml_retrain_bars", 3000),
        "last_run": _last_run,
        "last_result": _last_result,
        "running": _running,
        "stack": "PyTorch + MLflow",
    }
