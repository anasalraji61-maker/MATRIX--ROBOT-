"""V11 deep M5/M15 scalp scan for top cheap-scan symbols."""
from __future__ import annotations

import asyncio
import logging
from typing import Any

from config import get_settings
from tools.indicators import compute_indicators
from tools.liquidity_guard import check_spread, spread_pips
from tools.scalp_strategies import best_signal, evaluate_all
from tools.twelve_data import fetch_historical

logger = logging.getLogger("matrix.scalp_scanner")


async def _fetch_tf(symbol: str, tf: str, limit: int = 80) -> list[dict]:
    try:
        return await fetch_historical(symbol, limit=limit, timeframe=tf)
    except Exception as e:
        logger.debug("scalp fetch %s %s failed: %s", symbol, tf, e)
        return []


async def deep_scan_symbols(
    symbols: list[str],
    state: dict,
    *,
    session_kz: str = "",
) -> dict[str, Any]:
    settings = get_settings()
    tfs = [t.strip().upper() for t in settings.scalping_timeframes.split(",") if t.strip()]
    if not tfs:
        tfs = ["M5", "M15"]
    primary_tf = "M5" if "M5" in tfs else tfs[0]

    indicators_map = dict(state.get("indicators") or {})
    mtf_map = dict(state.get("mtf") or {})
    ict_map = dict(state.get("ict") or {})
    quotes = (state.get("market_data") or {}).get("quotes", [])
    quote_map = {q["symbol"]: q for q in quotes}

    candidates: list[dict] = []
    rejected: dict[str, str] = {}

    fetch_tasks = []
    for sym in symbols:
        fetch_tasks.append((sym, primary_tf, _fetch_tf(sym, primary_tf)))
    results = await asyncio.gather(*[t[2] for t in fetch_tasks], return_exceptions=True)

    for (sym, tf, _), bars_res in zip(fetch_tasks, results):
        if isinstance(bars_res, Exception) or not bars_res:
            ind = indicators_map.get(sym)
            if not ind:
                rejected[sym] = "no M5 bars and no H1 indicators"
                continue
            bars = None
        else:
            bars = bars_res
            ind = compute_indicators(sym, bars).model_dump()
            indicators_map[sym] = ind

        spread_ok, spread_reason = check_spread(sym, quote_map.get(sym), settings)
        if not spread_ok:
            rejected[sym] = spread_reason
            continue
        sp = spread_pips(sym, quote_map.get(sym))
        max_sp = float(settings.scalping_max_spread_pips_fx)
        if sp is not None and sp > max_sp:
            rejected[sym] = f"scalp spread {sp:.1f} > {max_sp}"
            continue

        hits = evaluate_all(
            sym, ind,
            bars=bars,
            mtf=mtf_map.get(sym),
            ict=ict_map.get(sym),
            session_kz=session_kz,
        )
        best = best_signal(hits)
        if not best:
            rejected[sym] = "no scalp strategy match"
            continue
        best["timeframe"] = tf
        best["spread_pips"] = sp
        candidates.append(best)

    candidates.sort(key=lambda x: x["strength"], reverse=True)
    return {
        "scalping_candidates_count": len(candidates),
        "top_scalping_candidates": candidates[:10],
        "scalp_deep_rejected": rejected,
        "deep_scanned_symbols": symbols,
    }
