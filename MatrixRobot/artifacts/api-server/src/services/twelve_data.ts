import * as https from "node:https";
import { URL } from "node:url";
import { logger } from "../lib/logger";

export interface TwelveDataQuote {
  symbol: string;
  price: number;
  change: number;
  changePct: number;
  timestamp: string;
}

export interface TwelveDataNewsItem {
  id: string;
  title: string;
  source: string;
  url: string;
  publishedAt: string;
  tickers: string[];
}

export interface TwelveDataConnectionResult {
  connected: boolean;
  message: string;
  latencyMs: number | null;
}

export interface OHLCBar {
  time: number;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
}

const TD_BASE = "https://api.twelvedata.com";

const WATCHED_PAIRS = ["EURUSD", "GBPUSD", "USDJPY", "XAUUSD"];

function tdSymbol(symbol: string): string {
  const clean = symbol.replace(/^C:/, "").replace(/^X:/, "").toUpperCase();
  if (clean.length === 6) return `${clean.slice(0, 3)}/${clean.slice(3)}`;
  return clean;
}

// Twelve Data WAF rejects requests from Node's undici fetch (returns 401
// "incorrect apikey" even with a valid key + spoofed UA). Native https.request
// works reliably — likely due to undici's default header set.
function httpsGetJson<T>(url: string): Promise<T | null> {
  return new Promise((resolve) => {
    const u = new URL(url);
    const req = https.request(
      {
        hostname: u.hostname,
        path: u.pathname + u.search,
        method: "GET",
        headers: { "User-Agent": "python-httpx/0.27.0", Accept: "*/*" },
        timeout: 8_000,
      },
      (res) => {
        const chunks: Buffer[] = [];
        res.on("data", (c: Buffer) => chunks.push(c));
        res.on("end", () => {
          const body = Buffer.concat(chunks).toString("utf8");
          if (!res.statusCode || res.statusCode >= 400) {
            logger.warn({ status: res.statusCode, path: u.pathname, body: body.slice(0, 200) }, "Twelve Data HTTP error");
            resolve(null);
            return;
          }
          try {
            resolve(JSON.parse(body) as T);
          } catch {
            logger.warn({ path: u.pathname }, "Twelve Data returned non-JSON");
            resolve(null);
          }
        });
      }
    );
    req.on("timeout", () => { req.destroy(); resolve(null); });
    req.on("error", (err) => {
      logger.error({ err, path: u.pathname }, "Twelve Data request failed");
      resolve(null);
    });
    req.end();
  });
}

async function tdFetch<T>(path: string, apiKey: string): Promise<T | null> {
  const sep = path.includes("?") ? "&" : "?";
  const url = `${TD_BASE}${path}${sep}apikey=${apiKey}`;
  const data = await httpsGetJson<T & { code?: number; status?: string; message?: string }>(url);
  if (!data) return null;
  if (
    (typeof data === "object" && data !== null && "code" in data && data.code) ||
    (typeof data === "object" && data !== null && "status" in data && data.status === "error")
  ) {
    logger.warn({ path, body: data }, "Twelve Data API error");
    return null;
  }
  return data as T;
}

export async function checkTwelveDataConnection(): Promise<TwelveDataConnectionResult> {
  const apiKey = process.env.TWELVE_DATA_API_KEY;
  if (!apiKey) {
    return {
      connected: false,
      message: "API key not configured — set TWELVE_DATA_API_KEY",
      latencyMs: null,
    };
  }

  const t0 = Date.now();
  const data = await tdFetch<{ close?: string; symbol?: string }>(
    "/quote?symbol=EUR/USD",
    apiKey
  );
  const latencyMs = Date.now() - t0;

  if (data && data.close) {
    return {
      connected: true,
      message: "Connected to Twelve Data — live forex data active",
      latencyMs,
    };
  }
  return {
    connected: false,
    message: "Twelve Data responded but returned no data",
    latencyMs,
  };
}

export async function fetchTwelveDataQuotes(): Promise<TwelveDataQuote[]> {
  const apiKey = process.env.TWELVE_DATA_API_KEY;
  if (!apiKey) return [];

  const symbolsParam = WATCHED_PAIRS.map(tdSymbol).join(",");
  const data = await tdFetch<Record<string, {
    symbol: string;
    close: string;
    change: string;
    percent_change: string;
    timestamp: number;
  }>>(`/quote?symbol=${encodeURIComponent(symbolsParam)}`, apiKey);

  if (!data) return [];

  return Object.values(data)
    .filter((q) => q && q.symbol && q.close)
    .map((q) => ({
      symbol: q.symbol.replace("/", ""),
      price: Number(q.close) || 0,
      change: Number(q.change) || 0,
      changePct: Number(q.percent_change) || 0,
      timestamp: q.timestamp
        ? new Date(q.timestamp * 1000).toISOString()
        : new Date().toISOString(),
    }));
}

export async function fetchTwelveDataOHLC(
  symbol: string,
  multiplier = 15,
  timespan = "minute",
  days = 3
): Promise<OHLCBar[]> {
  const apiKey = process.env.TWELVE_DATA_API_KEY;
  if (!apiKey) return [];

  const tdSym = tdSymbol(symbol);
  // Map polygon-style (multiplier, timespan) → Twelve Data interval
  const intervalMap: Record<string, string> = {
    minute: `${multiplier}min`,
    hour: `${multiplier}h`,
    day: `${multiplier}day`,
  };
  const interval = intervalMap[timespan] ?? `${multiplier}min`;

  // Estimate bar count for `days` of `interval`
  const barsPerDay: Record<string, number> = {
    "1min": 1440, "5min": 288, "15min": 96, "30min": 48, "45min": 32,
    "1h": 24, "2h": 12, "4h": 6, "1day": 1, "1week": 0.2, "1month": 0.03,
  };
  const outputsize = Math.min(
    500,
    Math.max(50, Math.ceil((barsPerDay[interval] ?? 96) * days))
  );

  const data = await tdFetch<{
    values?: Array<{
      datetime: string;
      open: string;
      high: string;
      low: string;
      close: string;
      volume?: string;
    }>;
  }>(
    `/time_series?symbol=${encodeURIComponent(tdSym)}&interval=${interval}&outputsize=${outputsize}&order=ASC`,
    apiKey
  );

  if (!data?.values?.length) return [];

  return data.values.map((b) => ({
    time: Math.floor(new Date(b.datetime + "Z").getTime() / 1000),
    open: Number(b.open) || 0,
    high: Number(b.high) || 0,
    low: Number(b.low) || 0,
    close: Number(b.close) || 0,
    volume: Number(b.volume ?? 0) || 0,
  }));
}

// Twelve Data Grow plan does NOT include a news endpoint.
// Keep a stub here so consumers can transparently swap.
// Real news still flows through services/polygon.ts (rate-limited but free).
export async function fetchTwelveDataNews(): Promise<TwelveDataNewsItem[]> {
  return [];
}
