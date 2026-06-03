import { logger } from "../lib/logger";

export interface PolygonQuote {
  symbol: string;
  price: number;
  change: number;
  changePct: number;
  timestamp: string;
}

export interface PolygonNewsItem {
  id: string;
  title: string;
  source: string;
  url: string;
  publishedAt: string;
  tickers: string[];
}

export interface PolygonConnectionResult {
  connected: boolean;
  message: string;
  latencyMs: number | null;
}

const POLYGON_BASE = "https://api.polygon.io";

// Forex pairs to monitor (using Polygon format: C:EURUSD)
const WATCHED_PAIRS = ["C:EURUSD", "C:GBPUSD", "C:USDJPY", "C:XAUUSD"];

async function polygonFetch<T>(
  path: string,
  apiKey: string
): Promise<T | null> {
  const url = `${POLYGON_BASE}${path}${path.includes("?") ? "&" : "?"}apiKey=${apiKey}`;
  const res = await fetch(url, { signal: AbortSignal.timeout(8_000) });
  if (!res.ok) {
    const body = await res.text();
    logger.warn({ status: res.status, path, body }, "Polygon API error");
    return null;
  }
  return res.json() as Promise<T>;
}

export async function checkPolygonConnection(): Promise<PolygonConnectionResult> {
  const apiKey = process.env.POLYGON_API_KEY;
  if (!apiKey) {
    return {
      connected: false,
      message: "API key not configured — set POLYGON_API_KEY",
      latencyMs: null,
    };
  }

  const t0 = Date.now();
  try {
    // Use previous-day aggregate as a lightweight connectivity check
    const yesterday = new Date(Date.now() - 86_400_000).toISOString().split("T")[0];
    const data = await polygonFetch<{ resultsCount?: number; results?: unknown[] }>(
      `/v2/aggs/ticker/C:EURUSD/range/1/day/${yesterday}/${yesterday}?limit=1`,
      apiKey
    );
    const latencyMs = Date.now() - t0;

    if (data !== null && (data.resultsCount != null || data.results != null)) {
      return {
        connected: true,
        message: "Connected to Polygon.io — live forex data active",
        latencyMs,
      };
    }
    return {
      connected: false,
      message: "Polygon responded but returned no data",
      latencyMs,
    };
  } catch (err) {
    logger.error({ err }, "Polygon connection check failed");
    return {
      connected: false,
      message: "Connection failed — check POLYGON_API_KEY",
      latencyMs: null,
    };
  }
}

export async function fetchPolygonQuotes(): Promise<PolygonQuote[]> {
  const apiKey = process.env.POLYGON_API_KEY;
  if (!apiKey) return [];

  try {
    const data = await polygonFetch<{
      tickers: Array<{
        ticker: string;
        day: { c: number; o: number };
        lastQuote: { a: number; b: number };
        todaysChangePerc: number;
        todaysChange: number;
        updated: number;
      }>;
    }>(
      `/v2/snapshot/locale/global/markets/forex/tickers?tickers=${WATCHED_PAIRS.join(",")}`,
      apiKey
    );

    if (!data?.tickers) return [];

    return data.tickers.map((t) => ({
      symbol: t.ticker.replace("C:", ""),
      price: t.lastQuote?.a ?? t.day?.c ?? 0,
      change: t.todaysChange ?? 0,
      changePct: t.todaysChangePerc ?? 0,
      timestamp: new Date(t.updated / 1_000_000).toISOString(),
    }));
  } catch (err) {
    logger.error({ err }, "Failed to fetch Polygon quotes");
    return [];
  }
}

export interface OHLCBar {
  time: number; // Unix seconds
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
}

export async function fetchPolygonOHLC(
  symbol: string,
  multiplier = 15,
  timespan = "minute",
  days = 3
): Promise<OHLCBar[]> {
  const apiKey = process.env.POLYGON_API_KEY;
  if (!apiKey) return [];

  const ticker = `C:${symbol}`;
  const to = new Date();
  const from = new Date(to.getTime() - days * 24 * 60 * 60 * 1000);
  const fromStr = from.toISOString().split("T")[0];
  const toStr = to.toISOString().split("T")[0];

  try {
    const data = await polygonFetch<{
      results: Array<{ t: number; o: number; h: number; l: number; c: number; v: number }>;
      status: string;
    }>(
      `/v2/aggs/ticker/${ticker}/range/${multiplier}/${timespan}/${fromStr}/${toStr}?sort=asc&limit=500`,
      apiKey
    );

    if (!data?.results?.length) return [];

    return data.results.map((b) => ({
      time: Math.floor(b.t / 1000), // ms → seconds
      open: b.o,
      high: b.h,
      low: b.l,
      close: b.c,
      volume: b.v,
    }));
  } catch (err) {
    logger.error({ err, symbol }, "Failed to fetch Polygon OHLC");
    return [];
  }
}

export async function fetchPolygonNews(tickerFilter?: string): Promise<PolygonNewsItem[]> {
  const apiKey = process.env.POLYGON_API_KEY;
  if (!apiKey) return [];

  const qs = tickerFilter
    ? `ticker=${encodeURIComponent(tickerFilter)}&limit=5&order=desc&sort=published_utc`
    : "limit=10&order=desc&sort=published_utc";

  try {
    const data = await polygonFetch<{
      results: Array<{
        id: string;
        title: string;
        publisher: { name: string };
        article_url: string;
        published_utc: string;
        tickers: string[];
      }>;
    }>(`/v2/reference/news?${qs}`, apiKey);

    if (!data?.results) return [];

    return data.results.map((n) => ({
      id: n.id,
      title: n.title,
      source: n.publisher?.name ?? "Polygon News",
      url: n.article_url,
      publishedAt: n.published_utc,
      tickers: n.tickers ?? [],
    }));
  } catch (err) {
    logger.error({ err }, "Failed to fetch Polygon news");
    return [];
  }
}

/** Fetch macro/forex/stocks news by querying key tickers and deduplicating */
export async function fetchForexNews(): Promise<PolygonNewsItem[]> {
  // Forex pairs + metals + equity ETFs + individual stocks
  const targets = [
    "C:EURUSD", "C:XAUUSD", "C:XAGUSD",   // forex + metals
    "SPY", "GLD", "SLV",                    // ETFs
    "AAPL", "TSLA", "NVDA", "AMZN", "MSFT", // stocks
  ];
  const results = await Promise.allSettled(
    targets.map((t) => fetchPolygonNews(t))
  );

  const seen = new Set<string>();
  const merged: PolygonNewsItem[] = [];

  for (const r of results) {
    if (r.status !== "fulfilled") continue;
    for (const item of r.value) {
      if (!seen.has(item.id)) {
        seen.add(item.id);
        merged.push(item);
      }
    }
  }

  // Sort newest first, cap at 12
  return merged
    .sort((a, b) => new Date(b.publishedAt).getTime() - new Date(a.publishedAt).getTime())
    .slice(0, 12);
}
