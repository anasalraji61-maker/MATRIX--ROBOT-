import httpx
import random
from datetime import datetime, timezone
from config import get_settings
from models.schemas import Quote, NewsItem

BASE = "https://api.polygon.io"

# Symbol type classification
_FOREX_SYMBOLS  = {"EURUSD", "GBPUSD", "USDJPY", "USDCHF", "AUDUSD",
                   "XAUUSD", "XAGUSD", "USDCAD", "NZDUSD"}
_STOCK_SYMBOLS  = {"AAPL", "TSLA", "AMZN", "NVDA", "MSFT", "GOOGL",
                   "META", "SPY", "QQQ"}

# Realistic base prices for mock / fallback
_BASE_PRICES: dict[str, float] = {
    "EURUSD": 1.0850, "GBPUSD": 1.2700, "USDJPY": 149.50,
    "USDCHF": 0.9050, "AUDUSD": 0.6580,
    "XAUUSD": 2340.0, "XAGUSD": 29.50,
    "USDCAD": 1.3650, "NZDUSD": 0.6120,
    "AAPL":  185.0,  "TSLA":  175.0,  "AMZN":  180.0,
    "NVDA":  875.0,  "MSFT":  415.0,  "GOOGL": 175.0,
    "META":  500.0,  "SPY":   520.0,  "QQQ":   440.0,
}


def _to_polygon_ticker(symbol: str) -> str:
    """Convert symbol name to Polygon.io ticker format."""
    if symbol in _FOREX_SYMBOLS:
        return f"C:{symbol}"
    return symbol  # stocks use plain ticker


async def fetch_quotes(symbols: list[str]) -> list[Quote]:
    settings = get_settings()
    if not settings.has_polygon:
        return _mock_quotes(symbols)

    forex  = [s for s in symbols if s in _FOREX_SYMBOLS]
    stocks = [s for s in symbols if s in _STOCK_SYMBOLS]
    results: list[Quote] = []

    async with httpx.AsyncClient(timeout=10.0) as client:
        # Forex + metals snapshot
        if forex:
            try:
                tickers = ",".join(f"C:{s}" for s in forex)
                r = await client.get(
                    f"{BASE}/v2/snapshot/locale/global/markets/forex/tickers",
                    params={"apiKey": settings.polygon_api_key, "tickers": tickers},
                )
                if r.status_code == 200:
                    for item in r.json().get("tickers", []):
                        sym = item.get("ticker", "").replace("C:", "")
                        lq  = item.get("lastQuote", {})
                        bid = lq.get("b", 0) or lq.get("bid", 0)
                        ask = lq.get("a", 0) or lq.get("ask", 0)
                        if bid == 0 and ask == 0:
                            day = item.get("day", {})
                            bid = ask = day.get("c", 0)
                        mid = (bid + ask) / 2 if (bid and ask) else 0
                        results.append(Quote(
                            symbol=sym,
                            bid=round(bid, 5),
                            ask=round(ask, 5),
                            mid=round(mid, 5),
                            change_pct=round(item.get("todaysChangePerc", 0) or 0, 3),
                            timestamp=datetime.now(timezone.utc).isoformat(),
                        ))
            except Exception:
                pass

        # Stocks snapshot
        if stocks:
            try:
                tickers = ",".join(stocks)
                r = await client.get(
                    f"{BASE}/v2/snapshot/locale/us/markets/stocks/tickers",
                    params={"apiKey": settings.polygon_api_key, "tickers": tickers},
                )
                if r.status_code == 200:
                    for item in r.json().get("tickers", []):
                        sym = item.get("ticker", "")
                        day = item.get("day", {})
                        price = day.get("c", 0)
                        results.append(Quote(
                            symbol=sym,
                            bid=round(price * 0.9999, 4),
                            ask=round(price * 1.0001, 4),
                            mid=round(price, 4),
                            change_pct=round(item.get("todaysChangePerc", 0) or 0, 3),
                            timestamp=datetime.now(timezone.utc).isoformat(),
                        ))
            except Exception:
                pass

    # Fill any missing symbols with mock data
    fetched = {q.symbol for q in results}
    missing = [s for s in symbols if s not in fetched]
    if missing:
        results.extend(_mock_quotes(missing))

    return results


# Polygon aggregation timeframe map
_TF_MAP: dict[str, tuple[int, str]] = {
    "M15": (15, "minute"),
    "H1":  (1,  "hour"),
    "H4":  (4,  "hour"),
    "D1":  (1,  "day"),
}


async def fetch_historical(symbol: str, limit: int = 120, timeframe: str = "H1") -> list[dict]:
    """Fetch OHLCV bars for `symbol` on `timeframe`.

    timeframe ∈ {M15, H1, H4, D1}. Falls back to mock bars when Polygon is
    unavailable or returns no data.
    """
    settings = get_settings()
    if not settings.has_polygon:
        return _mock_bars(symbol, limit)

    multiplier, span = _TF_MAP.get(timeframe, (1, "hour"))
    ticker = _to_polygon_ticker(symbol)
    async with httpx.AsyncClient(timeout=15.0) as client:
        try:
            r = await client.get(
                f"{BASE}/v2/aggs/ticker/{ticker}/range/{multiplier}/{span}/2024-01-01/{datetime.today().strftime('%Y-%m-%d')}",
                params={"apiKey": settings.polygon_api_key, "limit": limit, "sort": "asc"},
            )
            if r.status_code == 200:
                raw = r.json().get("results", [])
                if raw:
                    return [
                        {"open": b["o"], "high": b["h"], "low": b["l"],
                         "close": b["c"], "volume": b["v"]}
                        for b in raw
                    ]
        except Exception:
            pass

    return _mock_bars(symbol, limit)


# Tickers queried for macro/forex headlines (matches Node fetchForexNews strategy)
_FOREX_NEWS_TICKERS = [
    "C:EURUSD", "C:GBPUSD", "C:USDJPY", "C:XAUUSD", "C:XAGUSD",
    "C:USDCAD", "SPY", "GLD",
]


async def _fetch_news_for_ticker(
    client: httpx.AsyncClient, api_key: str, ticker: str, per_ticker: int = 5
) -> list[NewsItem]:
    try:
        r = await client.get(
            f"{BASE}/v2/reference/news",
            params={
                "apiKey": api_key,
                "ticker": ticker,
                "limit": per_ticker,
                "order": "desc",
                "sort": "published_utc",
            },
        )
        if r.status_code != 200:
            return []
        return [
            NewsItem(
                title=n.get("title", ""),
                summary=(n.get("description") or "")[:300],
                publisher=(n.get("publisher") or {}).get("name", "Unknown"),
                published_at=n.get("published_utc", ""),
            )
            for n in r.json().get("results", [])
            if n.get("title")
        ]
    except Exception:
        return []


async def fetch_forex_news(limit: int = 12) -> list[NewsItem]:
    """Fetch and dedupe real headlines from Polygon (forex + macro tickers)."""
    settings = get_settings()
    if not settings.has_polygon:
        return []

    seen_titles: set[str] = set()
    merged: list[NewsItem] = []

    async with httpx.AsyncClient(timeout=12.0) as client:
        # Also try a general feed (no ticker filter) — works on some plans
        try:
            r = await client.get(
                f"{BASE}/v2/reference/news",
                params={
                    "apiKey": settings.polygon_api_key,
                    "limit": min(limit, 10),
                    "order": "desc",
                    "sort": "published_utc",
                },
            )
            if r.status_code == 200:
                for n in r.json().get("results", []):
                    title = (n.get("title") or "").strip()
                    if not title or title in seen_titles:
                        continue
                    seen_titles.add(title)
                    merged.append(NewsItem(
                        title=title,
                        summary=(n.get("description") or "")[:300],
                        publisher=(n.get("publisher") or {}).get("name", "Unknown"),
                        published_at=n.get("published_utc", ""),
                    ))
        except Exception:
            pass

        if len(merged) < limit:
            import asyncio
            batches = await asyncio.gather(
                *[
                    _fetch_news_for_ticker(client, settings.polygon_api_key, t)
                    for t in _FOREX_NEWS_TICKERS
                ],
                return_exceptions=True,
            )
            for batch in batches:
                if isinstance(batch, Exception):
                    continue
                for item in batch:
                    key = item.title.strip()
                    if key and key not in seen_titles:
                        seen_titles.add(key)
                        merged.append(item)

    merged.sort(key=lambda x: x.published_at or "", reverse=True)
    return merged[:limit]


async def fetch_news(symbols: list[str], limit: int = 10) -> list[NewsItem]:
    """Legacy entry — prefer tools.news_feed.fetch_news in the brain cycle."""
    from config import get_settings
    items = await fetch_forex_news(limit=limit)
    if items:
        return items
    if getattr(get_settings(), "news_allow_mock", False):
        return _mock_news()
    return []



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
        NewsItem(title="NVIDIA beats earnings estimates on AI chip demand",
                 summary="NVDA reports record revenue driven by data center growth.",
                 publisher="CNBC", published_at=now),
        NewsItem(title="Apple launches new AI features in iOS update",
                 summary="AAPL shares rise on strong developer adoption forecasts.",
                 publisher="Bloomberg", published_at=now),
    ]
