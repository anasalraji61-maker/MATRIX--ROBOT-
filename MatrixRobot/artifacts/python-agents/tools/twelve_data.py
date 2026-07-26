"""
Twelve Data client — drop-in replacement for tools.polygon.

Provides the same three async fetchers (fetch_quotes, fetch_historical,
fetch_news) with the same return shapes, plus an in-memory TTL cache and
a global concurrency limiter to stay under the Grow plan's 55 req/min cap.

Symbol mapping
--------------
- Forex / metals: "EURUSD" -> "EUR/USD", "XAUUSD" -> "XAU/USD"
- Stocks:         "AAPL"   -> "AAPL"

Timeframes
----------
M15 -> 15min, H1 -> 1h, H4 -> 4h, D1 -> 1day
"""
from __future__ import annotations

import asyncio
import random
import time
import httpx
from datetime import datetime, timezone
from typing import Any

from config import get_settings
from models.schemas import Quote, NewsItem


BASE = "https://api.twelvedata.com"

from tools.symbol_registry import FOREX_SET, OIL, METALS, INDICES

# US indices + oil: broker symbol -> Twelve Data ticker
_SPECIAL_TO_TD: dict[str, str] = {
    "US30":  "DJI",        # Dow Jones
    "US500": "SPX",        # S&P 500
    "USTEC": "NDX",        # Nasdaq 100
    "USOIL": "WTI/USD",    # WTI crude
    "UKOIL": "BRENT/USD",  # Brent crude
}
_TD_TO_SPECIAL: dict[str, str] = {v.replace("/", ""): k for k, v in _SPECIAL_TO_TD.items()}
_TD_TO_SPECIAL.update({"DJI": "US30", "SPX": "US500", "NDX": "USTEC", "CL": "USOIL", "BZ": "UKOIL"})

_BASE_PRICES: dict[str, float] = {
    "EURUSD": 1.0850, "GBPUSD": 1.2700, "USDJPY": 149.50,
    "USDCHF": 0.9050, "AUDUSD": 0.6580, "NZDUSD": 0.6120,
    "USDCAD": 1.3650,
    "EURGBP": 0.8540, "EURJPY": 162.30, "GBPJPY": 190.00,
    "EURAUD": 1.6500, "EURCHF": 0.9820, "AUDJPY": 98.40,
    "CHFJPY": 165.20, "CADJPY": 109.50, "NZDJPY": 91.50,
    "GBPCHF": 1.1490, "AUDCAD": 0.8980, "AUDNZD": 1.0750,
    "EURCAD": 1.4800, "EURNZD": 1.7700, "EURSEK": 11.50, "EURNOK": 11.80,
    "EURPLN": 4.30, "EURHUF": 395.0, "EURTRY": 35.0, "EURSGD": 1.46,
    "GBPAUD": 1.9300, "GBPCAD": 1.7350, "GBPNZD": 2.0750, "GBPSEK": 13.50,
    "GBPSGD": 1.71, "AUDCHF": 0.5950, "AUDSGD": 0.8850, "NZDCAD": 0.8350,
    "NZDCHF": 0.5550, "CADCHF": 0.6630, "CHFSGD": 1.49,
    "USDSEK": 10.60, "USDNOK": 10.90, "USDTRY": 32.20, "USDZAR": 18.50,
    "USDMXN": 17.20, "USDPLN": 3.97, "USDHUF": 365.0, "USDSGD": 1.3450,
    "USDHKD": 7.80, "USDCNH": 7.25,
    "XAUUSD": 2340.0, "XAGUSD": 29.50,
    "USOIL": 78.50, "UKOIL": 82.00,
    "US30": 42500.0, "US500": 5800.0, "USTEC": 20500.0,
}

_TF_MAP: dict[str, str] = {
    "M15": "15min",
    "H1":  "1h",
    "H4":  "4h",
    "D1":  "1day",
}

# Cache TTL by timeframe (seconds). Bars don't change every second so longer
# TTLs on higher TFs save dozens of req/cycle.
_BAR_TTL: dict[str, int] = {
    "M15": 120,    # 2 min
    "H1":  300,    # 5 min
    "H4":  1800,   # 30 min
    "D1":  7200,   # 2 hours
}
_QUOTE_TTL = 30      # seconds
_NEWS_TTL = 300      # 5 min

# Token bucket — Twelve Data Grow ≈ 55 req/min; stay under with margin.
_HTTP_SEMAPHORE = asyncio.Semaphore(8)
_rate_lock = asyncio.Lock()
_rate_timestamps: list[float] = []
_RATE_MAX_PER_MINUTE = 45


async def _acquire_rate_slot() -> None:
    """Block until a request slot is available under the per-minute cap."""
    while True:
        async with _rate_lock:
            now = time.time()
            _rate_timestamps[:] = [t for t in _rate_timestamps if now - t < 60.0]
            if len(_rate_timestamps) < _RATE_MAX_PER_MINUTE:
                _rate_timestamps.append(now)
                return
            wait = 60.0 - (now - _rate_timestamps[0])
        await asyncio.sleep(min(max(wait, 0.05), 2.0))

# Module-level caches: {key: (value, expires_at_epoch)}
_bars_cache: dict[str, tuple[list[dict], float]] = {}
_quotes_cache: dict[str, tuple[Quote, float]] = {}
_news_cache: dict[str, tuple[list[NewsItem], float]] = {}
_last_meta: dict[str, Any] = {
    "quotes_mock_symbols": [],
    "bars_mock_symbols": [],
    "quotes_source": "none",
}


def get_data_meta() -> dict[str, Any]:
    return dict(_last_meta)


def reset_data_meta() -> None:
    """Clear mock/source tracking at the start of each data cycle."""
    _last_meta["quotes_mock_symbols"] = []
    _last_meta["bars_mock_symbols"] = []
    _last_meta["quotes_source"] = "none"


def _clear_bars_mock(symbol: str) -> None:
    prev = set(_last_meta.get("bars_mock_symbols") or [])
    prev.discard(symbol.upper())
    _last_meta["bars_mock_symbols"] = sorted(prev)


def _now() -> float:
    return time.time()


def _to_td_symbol(symbol: str) -> str:
    """Convert internal symbol form to Twelve Data form."""
    if symbol in _SPECIAL_TO_TD:
        return _SPECIAL_TO_TD[symbol]
    if symbol in FOREX_SET and len(symbol) == 6:
        return f"{symbol[:3]}/{symbol[3:]}"
    if symbol in METALS and len(symbol) == 6:
        return f"{symbol[:3]}/{symbol[3:]}"
    return symbol


def _from_td_symbol(td_symbol: str) -> str:
    clean = td_symbol.replace("/", "").upper()
    return _TD_TO_SPECIAL.get(clean, _TD_TO_SPECIAL.get(td_symbol.upper(), clean))


# ─────────────────────────── Quotes ────────────────────────────

async def fetch_quotes(symbols: list[str]) -> list[Quote]:
    settings = get_settings()
    _last_meta["quotes_mock_symbols"] = []
    if not settings.has_twelve_data:
        _last_meta["quotes_source"] = "mock"
        _last_meta["quotes_mock_symbols"] = list(symbols)
        return _mock_quotes(symbols)

    results: list[Quote] = []
    missing: list[str] = []
    for s in symbols:
        cached = _quotes_cache.get(s)
        if cached and cached[1] > _now():
            results.append(cached[0])
        else:
            missing.append(s)

    if not missing:
        return results

    # Twelve Data /quote accepts comma-separated symbols and returns a dict
    # keyed by symbol when multiple, or a single object when one.
    td_syms = ",".join(_to_td_symbol(s) for s in missing)
    try:
        async with _HTTP_SEMAPHORE:
            await _acquire_rate_slot()
            async with httpx.AsyncClient(timeout=10.0) as client:
                r = await client.get(
                    f"{BASE}/quote",
                    params={"symbol": td_syms, "apikey": settings.twelve_data_api_key},
                )
        if r.status_code == 200:
            data = r.json()
            # Single result -> wrap into dict by symbol
            if isinstance(data, dict) and "symbol" in data:
                data = {data["symbol"]: data}
            if isinstance(data, dict):
                for td_sym, item in data.items():
                    if not isinstance(item, dict) or item.get("status") == "error":
                        continue
                    sym = _from_td_symbol(td_sym)
                    q = _parse_quote(sym, item)
                    if q:
                        results.append(q)
                        _quotes_cache[sym] = (q, _now() + _QUOTE_TTL)
    except Exception:
        pass

    # Any still missing -> mock
    fetched = {q.symbol for q in results}
    still_missing = [s for s in symbols if s not in fetched]
    if still_missing:
        results.extend(_mock_quotes(still_missing))
        _last_meta["quotes_mock_symbols"] = still_missing
        _last_meta["quotes_source"] = "mixed" if fetched else "mock"
    else:
        _last_meta["quotes_source"] = "twelve_data"

    return results


def _parse_quote(symbol: str, item: dict) -> Quote | None:
    try:
        close = float(item.get("close") or 0)
        if close <= 0:
            return None
        change_pct = float(item.get("percent_change") or 0)
        bid = float(item.get("bid") or close * 0.9999)
        ask = float(item.get("ask") or close * 1.0001)
        if bid <= 0:
            bid = close * 0.9999
        if ask <= 0:
            ask = close * 1.0001
        mid = (bid + ask) / 2
        return Quote(
            symbol=symbol,
            bid=round(bid, 5),
            ask=round(ask, 5),
            mid=round(mid, 5),
            change_pct=round(change_pct, 3),
            timestamp=datetime.now(timezone.utc).isoformat(),
        )
    except (TypeError, ValueError):
        return None


# ──────────────────────── Historical bars ──────────────────────

async def fetch_historical(symbol: str, limit: int = 120, timeframe: str = "H1") -> list[dict]:
    settings = get_settings()
    if not settings.has_twelve_data:
        mock = _mock_bars(symbol, limit)
        prev = set(_last_meta.get("bars_mock_symbols") or [])
        prev.add(symbol)
        _last_meta["bars_mock_symbols"] = sorted(prev)
        return mock

    cache_key = f"{symbol}:{timeframe}:{limit}"
    cached = _bars_cache.get(cache_key)
    if cached and cached[1] > _now():
        return cached[0]

    interval = _TF_MAP.get(timeframe, "1h")
    td_sym = _to_td_symbol(symbol)
    try:
        async with _HTTP_SEMAPHORE:
            await _acquire_rate_slot()
            async with httpx.AsyncClient(timeout=15.0) as client:
                r = await client.get(
                    f"{BASE}/time_series",
                    params={
                        "symbol": td_sym,
                        "interval": interval,
                        "outputsize": limit,
                        "order": "ASC",
                        "apikey": settings.twelve_data_api_key,
                    },
                )
        if r.status_code == 200:
            data = r.json()
            if isinstance(data, dict) and data.get("status") != "error":
                vals = data.get("values") or []
                bars = []
                for v in vals:
                    try:
                        bars.append({
                            "open":   float(v["open"]),
                            "high":   float(v["high"]),
                            "low":    float(v["low"]),
                            "close":  float(v["close"]),
                            "volume": float(v.get("volume", 0) or 0),
                        })
                    except (KeyError, TypeError, ValueError):
                        continue
                if bars:
                    ttl = _BAR_TTL.get(timeframe, 300)
                    _bars_cache[cache_key] = (bars, _now() + ttl)
                    _clear_bars_mock(symbol)
                    return bars
    except Exception:
        pass

    prev = set(_last_meta.get("bars_mock_symbols") or [])
    prev.add(symbol)
    _last_meta["bars_mock_symbols"] = sorted(prev)
    return _mock_bars(symbol, limit)


# ────────────────────────────── News ───────────────────────────
# Twelve Data Grow has no news API — delegate to unified news_feed (Polygon).

async def fetch_news(symbols: list[str], limit: int = 10) -> list[NewsItem]:
    from tools.news_feed import fetch_news as _unified_fetch_news
    return await _unified_fetch_news(symbols, limit=limit)



# ────────────────────────── Fallbacks ──────────────────────────

def _mock_quotes(symbols: list[str]) -> list[Quote]:
    now = datetime.now(timezone.utc).isoformat()
    return [
        Quote(
            symbol=s,
            bid=round(_BASE_PRICES.get(s, 1.0) * random.uniform(0.9990, 0.9999), 5),
            ask=round(_BASE_PRICES.get(s, 1.0) * random.uniform(1.0001, 1.0010), 5),
            mid=round(_BASE_PRICES.get(s, 1.0) * random.uniform(0.9995, 1.0005), 5),
            change_pct=round(random.uniform(-0.4, 0.4), 3),
            timestamp=now,
        )
        for s in symbols
    ]


def _mock_bars(symbol: str, limit: int) -> list[dict]:
    base = _BASE_PRICES.get(symbol, 1.0)
    bars = []
    price = base
    for _ in range(limit):
        change = random.uniform(-0.002, 0.002)
        open_p  = price
        close_p = price * (1 + change)
        high_p  = max(open_p, close_p) * random.uniform(1.000, 1.001)
        low_p   = min(open_p, close_p) * random.uniform(0.999, 1.000)
        bars.append({"open": open_p, "high": high_p,
                     "low": low_p, "close": close_p,
                     "volume": random.randint(1000, 50000)})
        price = close_p
    return bars


def _mock_news() -> list[NewsItem]:
    now = datetime.now(timezone.utc).isoformat()
    return [
        NewsItem(title="Fed holds rates steady amid inflation concerns",
                 summary="Federal Reserve keeps benchmark rate unchanged.",
                 publisher="Reuters", published_at=now),
        NewsItem(title="EUR/USD edges higher on ECB rate outlook",
                 summary="Euro gains on expectations ECB will delay rate cuts.",
                 publisher="Bloomberg", published_at=now),
        NewsItem(title="Gold surges as safe-haven demand rises",
                 summary="XAU/USD climbs above $2,340 driven by geopolitical risk.",
                 publisher="MarketWatch", published_at=now),
        NewsItem(title="Silver outperforms gold on industrial demand",
                 summary="XAG/USD up 2% as manufacturing data beats expectations.",
                 publisher="Reuters", published_at=now),
    ]


def cache_stats() -> dict[str, Any]:
    """Diagnostic helper for /agents/data-source endpoint."""
    return {
        "provider": "twelve_data",
        "bars_cached": len(_bars_cache),
        "quotes_cached": len(_quotes_cache),
        "news_cached": len(_news_cache),
    }
