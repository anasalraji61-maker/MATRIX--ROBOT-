import { Router } from "express";
import * as https from "node:https";
import * as http from "node:http";
import { URL } from "node:url";
import { logger } from "../lib/logger";

const router = Router();

const PYTHON_URL = process.env.PYTHON_AGENT_URL ?? "http://127.0.0.1:8000";

let dailySnapshot: { date: string; orUsageAtDayStart: number | null } = {
  date: "",
  orUsageAtDayStart: null,
};

function todayUTC() {
  return new Date().toISOString().slice(0, 10);
}

function httpGetJson<T>(rawUrl: string): Promise<T | null> {
  return new Promise((resolve) => {
    const u = new URL(rawUrl);
    const lib = u.protocol === "https:" ? https : http;
    const req = lib.request(
      {
        hostname: u.hostname,
        port: u.port || undefined,
        path: u.pathname + u.search,
        method: "GET",
        headers: {
          "User-Agent": "python-httpx/0.27.0",
          Accept: "*/*",
        },
        timeout: 8_000,
      },
      (res) => {
        const chunks: Buffer[] = [];
        res.on("data", (c: Buffer) => chunks.push(c));
        res.on("end", () => {
          const body = Buffer.concat(chunks).toString("utf8");
          try {
            resolve(JSON.parse(body) as T);
          } catch {
            resolve(null);
          }
        });
      }
    );
    req.on("timeout", () => {
      req.destroy();
      resolve(null);
    });
    req.on("error", (err) => {
      logger.warn({ err }, "httpGetJson error");
      resolve(null);
    });
    req.end();
  });
}

async function fetchOpenRouterUsage() {
  const resp = await httpGetJson<{
    available: boolean;
    usage_usd?: number;
    limit?: number | null;
  }>(`${PYTHON_URL}/agents/usage/openrouter`);

  if (!resp || !resp.available || typeof resp.usage_usd !== "number") {
    return { available: false };
  }

  const today = todayUTC();
  if (dailySnapshot.date !== today) {
    dailySnapshot = { date: today, orUsageAtDayStart: resp.usage_usd };
  }

  const totalUsage = resp.usage_usd;
  const dailySpent = totalUsage - (dailySnapshot.orUsageAtDayStart ?? totalUsage);
  const initialBalance = parseFloat(
    process.env.OPENROUTER_INITIAL_BALANCE ?? "49.74"
  );
  const remaining = Math.max(0, initialBalance - totalUsage);

  return {
    available: true,
    total_spent_usd: Math.round(totalUsage * 10000) / 10000,
    daily_spent_usd: Math.round(dailySpent * 10000) / 10000,
    remaining_usd: Math.round(remaining * 100) / 100,
    initial_balance_usd: initialBalance,
  };
}

async function fetchTwelveDataUsage() {
  const key = process.env.TWELVE_DATA_API_KEY;
  if (!key) return { available: false };

  const data = await httpGetJson<{
    current_usage?: number;
    plan_limit?: number;
    plan_name?: string;
    timestamp?: string;
  }>(`https://api.twelvedata.com/api_usage?apikey=${key}`);

  if (!data || typeof data.current_usage !== "number") {
    return { available: false };
  }

  return {
    available: true,
    credits_used: data.current_usage,
    credits_limit: data.plan_limit ?? 800,
    plan: data.plan_name ?? "Grow",
    timestamp: data.timestamp ?? null,
  };
}

router.get("/usage", async (req, res) => {
  const [openrouter, twelve_data] = await Promise.all([
    fetchOpenRouterUsage(),
    fetchTwelveDataUsage(),
  ]);
  res.json({ openrouter, twelve_data });
});

export default router;
