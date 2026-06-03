import Redis from "ioredis";
import { logger } from "../lib/logger";

let client: Redis | null = null;
let connectionState: "disconnected" | "connecting" | "connected" | "error" =
  "disconnected";
let lastError = "";

export function getRedisClient(): Redis | null {
  const url = process.env.REDIS_URL;
  if (!url) return null;

  if (client && connectionState === "connected") return client;

  if (!client) {
    connectionState = "connecting";
    client = new Redis(url, {
      maxRetriesPerRequest: 2,
      connectTimeout: 5_000,
      lazyConnect: false,
      tls: url.startsWith("rediss://") ? {} : undefined,
    });

    client.on("connect", () => {
      connectionState = "connected";
      logger.info("Redis connected");
    });

    client.on("error", (err: Error) => {
      connectionState = "error";
      lastError = err.message;
      logger.error({ err }, "Redis connection error");
    });

    client.on("close", () => {
      connectionState = "disconnected";
      logger.warn("Redis connection closed");
    });
  }

  return client;
}

export interface RedisConnectionResult {
  connected: boolean;
  message: string;
  latencyMs: number | null;
}

export async function checkRedisConnection(): Promise<RedisConnectionResult> {
  const url = process.env.REDIS_URL;
  if (!url) {
    // No Redis configured → Python agents use in-memory cache as designed.
    // Report this as a healthy "in-memory" mode rather than a failure.
    return {
      connected: true,
      message: "In-memory cache (Redis not configured)",
      latencyMs: 0,
    };
  }

  const redis = getRedisClient();
  if (!redis) {
    return { connected: false, message: "Redis client failed to initialise", latencyMs: null };
  }

  try {
    const t0 = Date.now();
    await redis.ping();
    const latencyMs = Date.now() - t0;
    return {
      connected: true,
      message: "Connected to Redis — agent memory active",
      latencyMs,
    };
  } catch (err) {
    logger.error({ err }, "Redis ping failed");
    return {
      connected: false,
      message: `Redis ping failed: ${lastError || String(err)}`,
      latencyMs: null,
    };
  }
}

// ──────────────────────────────────────────
// Agent memory helpers
// ──────────────────────────────────────────

const KEY_MARKET_SNAPSHOT = "trading:market_snapshot";
const KEY_AGENT_DECISIONS = "trading:agent_decisions";
const TTL_SECONDS = 300; // 5 minutes

export async function saveMarketSnapshot(data: unknown): Promise<void> {
  const redis = getRedisClient();
  if (!redis) return;
  await redis.setex(KEY_MARKET_SNAPSHOT, TTL_SECONDS, JSON.stringify(data));
}

export async function loadMarketSnapshot<T>(): Promise<T | null> {
  const redis = getRedisClient();
  if (!redis) return null;
  const raw = await redis.get(KEY_MARKET_SNAPSHOT);
  return raw ? (JSON.parse(raw) as T) : null;
}

export async function saveAgentDecisions(decisions: unknown[]): Promise<void> {
  const redis = getRedisClient();
  if (!redis) return;
  await redis.setex(KEY_AGENT_DECISIONS, TTL_SECONDS, JSON.stringify(decisions));
}

export async function loadAgentDecisions<T>(): Promise<T[] | null> {
  const redis = getRedisClient();
  if (!redis) return null;
  const raw = await redis.get(KEY_AGENT_DECISIONS);
  return raw ? (JSON.parse(raw) as T[]) : null;
}
