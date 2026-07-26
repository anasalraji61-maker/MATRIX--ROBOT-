"""
Data Agent — fetches live quotes, historical bars, news, and computes the
full analytics suite (indicators, multi-timeframe trends, volatility regimes,
correlation report, economic calendar) all in parallel.

Runs first in the LangGraph pipeline; all downstream agents depend on its output.
"""
import asyncio
from config import get_settings
from tools.universe_manager import active_symbols, is_full_power
from tools.twelve_data import fetch_quotes, fetch_historical, get_data_meta, reset_data_meta
from tools.news_feed import fetch_news, get_last_meta
from tools.indicators import compute_indicators, format_indicators_summary
from tools.multi_timeframe import compute_mtf, format_mtf_summary
from tools.volatility_regime import classify as classify_vol
from tools.ict_smc import analyze as analyze_ict, format_summary as format_ict_summary
from tools import correlation, economic_calendar, account_state, accounts as accounts_mod
import runtime_state


async def run(state: dict) -> dict:
    settings = get_settings()
    symbols = active_symbols(settings) if is_full_power(settings) else settings.symbol_list
    reset_data_meta()

    # Quotes + news + live account in parallel
    quotes, news, acct = await asyncio.gather(
        fetch_quotes(symbols),
        fetch_news(symbols),
        account_state.refresh_account(),
    )

    # Drop ghost positions closed on MT5 but still in memory (blocks FN margin cap)
    mode = runtime_state.get_mode() or settings.trading_state
    if mode == "ACTIVE" and settings.mt5_bridge_url:
        from tools.symbol_specs import refresh_broker_specs
        await refresh_broker_specs(symbols, settings.mt5_bridge_url)
    if mode == "ACTIVE":
        await account_state.sync_open_positions()
        for acct_cfg in accounts_mod.enabled_accounts():
            if acct_cfg.id != "primary" and acct_cfg.bridge_url:
                await account_state.sync_open_positions(
                    account_id=acct_cfg.id,
                    bridge_url=acct_cfg.bridge_url,
                )

    # Per-symbol primary bars, then indicators + vol regime
    primary_tf = str(getattr(settings, "primary_timeframe", "H1") or "H1").upper()
    bar_limit = 240 if primary_tf == "H1" else (300 if primary_tf == "M5" else 200)
    primary_bars = await asyncio.gather(
        *[fetch_historical(s, limit=bar_limit, timeframe=primary_tf) for s in symbols]
    )
    indicators_list = [compute_indicators(s, bars) for s, bars in zip(symbols, primary_bars)]
    vol_regimes = [classify_vol(s, bars) for s, bars in zip(symbols, primary_bars)]

    # Multi-timeframe — top N symbols only (saves Twelve Data quota)
    mtf_views: list = []
    if settings.multi_timeframe_enabled:
        if is_full_power(settings):
            top_n = max(1, int(getattr(settings, "deep_analysis_top_n", 15)))
        else:
            top_n = max(1, int(getattr(settings, "mtf_max_symbols", 8)))
        ranked = sorted(
            indicators_list,
            key=lambda i: float(getattr(i, "adx_14", 0) or 0),
            reverse=True,
        )
        mtf_symbols = [i.symbol for i in ranked[:top_n]]
        bars_by_sym = dict(zip(symbols, primary_bars))
        mtf_views = await asyncio.gather(*[
            compute_mtf(s, h1_bars=bars_by_sym.get(s)) for s in mtf_symbols
        ])
        mtf_map = {m.symbol: m.model_dump() for m in mtf_views}
        for s in symbols:
            if s not in mtf_map:
                mtf_map[s] = {
                    "symbol": s,
                    "timeframes": [],
                    "consensus": "neutral",
                    "aligned_count": 0,
                    "score": 0.0,
                }
        mtf_summaries = {}
        for s in symbols:
            view = mtf_map.get(s)
            if view and view.get("timeframes"):
                from models.schemas import MultiTimeframeView
                mtf_summaries[s] = format_mtf_summary(MultiTimeframeView(**view))
            else:
                mtf_summaries[s] = f"MTF[{s}]: neutral (not in top-{top_n} MTF batch)"
    else:
        mtf_map = {}
        mtf_summaries = {}

    # Correlation + economic calendar (cheap, sync-ish)
    corr_report = correlation.build_report() if settings.correlation_guard_enabled else None
    calendar = economic_calendar.get_calendar() if settings.economic_calendar_enabled else None

    # Build dashboards / summaries
    indicators_map = {ind.symbol: ind.model_dump() for ind in indicators_list}
    indicators_summaries = {
        s: format_indicators_summary(ind) for s, ind in zip(symbols, indicators_list)
    }
    vol_map = {v.symbol: v.model_dump() for v in vol_regimes}

    # ICT / SMC analysis on the same H1 bars (pure-python, no extra fetch)
    ict_map: dict = {}
    ict_summaries: dict = {}
    if settings.ict_smc_enabled:
        ict_list = [analyze_ict(s, bars) for s, bars in zip(symbols, primary_bars)]
        ict_map = {i.symbol: i.model_dump() for i in ict_list}
        ict_summaries = {i.symbol: format_ict_summary(i) for i in ict_list}

    news_meta = get_last_meta()
    td_meta = get_data_meta()
    market_data = {
        "quotes": [q.model_dump() for q in quotes],
        "news": [n.model_dump() for n in news],
        "news_source": news_meta.get("source", "unknown"),
        "news_count": len(news),
        "data_quality": {
            "quotes_source": td_meta.get("quotes_source", "unknown"),
            "quotes_mock_symbols": td_meta.get("quotes_mock_symbols", []),
            "bars_mock_symbols": td_meta.get("bars_mock_symbols", []),
        },
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
