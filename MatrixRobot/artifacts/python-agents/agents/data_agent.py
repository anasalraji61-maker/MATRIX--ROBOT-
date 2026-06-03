"""
Data Agent — fetches live quotes, historical bars, news, and computes the
full analytics suite (indicators, multi-timeframe trends, volatility regimes,
correlation report, economic calendar) all in parallel.

Runs first in the LangGraph pipeline; all downstream agents depend on its output.
"""
import asyncio
from config import get_settings
from tools.twelve_data import fetch_quotes, fetch_historical, fetch_news
from tools.indicators import compute_indicators, format_indicators_summary
from tools.multi_timeframe import compute_mtf, format_mtf_summary
from tools.volatility_regime import classify as classify_vol
from tools.ict_smc import analyze as analyze_ict, format_summary as format_ict_summary
from tools import correlation, economic_calendar, account_state


async def run(state: dict) -> dict:
    settings = get_settings()
    symbols = settings.symbol_list

    # Quotes + news + live account in parallel
    quotes, news, acct = await asyncio.gather(
        fetch_quotes(symbols),
        fetch_news(symbols),
        account_state.refresh_account(),
    )

    # Per-symbol primary bars (H1), then indicators + vol regime
    primary_bars = await asyncio.gather(*[fetch_historical(s, limit=240, timeframe="H1") for s in symbols])
    indicators_list = [compute_indicators(s, bars) for s, bars in zip(symbols, primary_bars)]
    vol_regimes = [classify_vol(s, bars) for s, bars in zip(symbols, primary_bars)]

    # Multi-timeframe consensus per symbol (parallel)
    mtf_views: list = []
    if settings.multi_timeframe_enabled:
        mtf_views = await asyncio.gather(*[compute_mtf(s) for s in symbols])

    # Correlation + economic calendar (cheap, sync-ish)
    corr_report = correlation.build_report() if settings.correlation_guard_enabled else None
    calendar = economic_calendar.get_calendar() if settings.economic_calendar_enabled else None

    # Build dashboards / summaries
    indicators_map = {ind.symbol: ind.model_dump() for ind in indicators_list}
    indicators_summaries = {
        s: format_indicators_summary(ind) for s, ind in zip(symbols, indicators_list)
    }
    mtf_map = {m.symbol: m.model_dump() for m in mtf_views}
    mtf_summaries = {m.symbol: format_mtf_summary(m) for m in mtf_views}
    vol_map = {v.symbol: v.model_dump() for v in vol_regimes}

    # ICT / SMC analysis on the same H1 bars (pure-python, no extra fetch)
    ict_map: dict = {}
    ict_summaries: dict = {}
    if settings.ict_smc_enabled:
        ict_list = [analyze_ict(s, bars) for s, bars in zip(symbols, primary_bars)]
        ict_map = {i.symbol: i.model_dump() for i in ict_list}
        ict_summaries = {i.symbol: format_ict_summary(i) for i in ict_list}

    market_data = {
        "quotes": [q.model_dump() for q in quotes],
        "news": [n.model_dump() for n in news],
        "symbols": symbols,
    }

    # Cache bars (as plain list-of-dicts) so the agentic brain's tool
    # registry can run on-demand strategies (Wyckoff/Elliott/Harmonic/VP/
    # Chart Patterns) without re-fetching from Polygon.
    bars_cache = {
        s: [b.model_dump() if hasattr(b, "model_dump") else dict(b) for b in bars]
        for s, bars in zip(symbols, primary_bars)
    }

    return {
        **state,
        "market_data": market_data,
        "indicators": indicators_map,
        "indicators_summaries": indicators_summaries,
        "mtf": mtf_map,
        "mtf_summaries": mtf_summaries,
        "ict": ict_map,
        "ict_summaries": ict_summaries,
        "volatility_regimes": vol_map,
        "correlation_report": corr_report.model_dump() if corr_report else None,
        "economic_calendar": calendar.model_dump() if calendar else None,
        "symbols_analyzed": symbols,
        "account": acct,
        "_bars_h1": bars_cache,
    }
