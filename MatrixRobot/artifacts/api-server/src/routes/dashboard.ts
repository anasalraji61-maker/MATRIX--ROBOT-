import { Router, type IRouter } from "express";
import { logger } from "../lib/logger";
import { fetchPolygonNews } from "../services/polygon";
import {
  checkTwelveDataConnection,
  fetchTwelveDataQuotes,
  fetchTwelveDataOHLC,
} from "../services/twelve_data";
import { checkRedisConnection, saveMarketSnapshot, saveAgentDecisions, loadAgentDecisions } from "../services/redis";
import {
  runAnalysisAgent,
  runRiskAgent,
  runSupervisorAgent,
  isOpenAIConfigured,
  type AgentDecision,
} from "../services/openai-agent";

const router: IRouter = Router();

// ── Trading state (in-memory, overrideable via env) ─────────
const TRADING_STATE = (process.env.TRADING_STATE as "PAPER_MODE" | "ACTIVE" | "FROZEN") ?? "PAPER_MODE";
const DAILY_LIMIT_PCT = parseFloat(process.env.DAILY_LIMIT_PCT ?? "2.5");
const TOTAL_LIMIT_PCT = parseFloat(process.env.TOTAL_LIMIT_PCT ?? "8.0");

let lastRefreshed = new Date().toISOString();
let refreshCount = 0;

// ── Demo account (replaced by real MT5 values when connected) ─
let demoBalance = 10000;
let demoDailyDrawdown = 0;
let demoTotalDrawdown = 0;

function randomiseDemoValues() {
  demoDailyDrawdown = +(Math.random() * 1.8 + 0.1).toFixed(2);
  demoTotalDrawdown = +(Math.random() * 4.5 + 0.5).toFixed(2);
}
randomiseDemoValues();

// ── Static fallback data ─────────────────────────────────────
const FALLBACK_NEWS = [
  {
    id: "news-1",
    title: "Fed holds rates steady, signals patience on cuts",
    source: "Reuters",
    impact: "HIGH" as const,
    publishedAt: new Date(Date.now() - 1000 * 60 * 30).toISOString(),
    currency: "USD",
  },
  {
    id: "news-2",
    title: "EUR/USD consolidates ahead of ECB minutes",
    source: "FXStreet",
    impact: "MEDIUM" as const,
    publishedAt: new Date(Date.now() - 1000 * 60 * 75).toISOString(),
    currency: "EUR",
  },
  {
    id: "news-3",
    title: "Gold edges higher as dollar weakens",
    source: "Bloomberg",
    impact: "LOW" as const,
    publishedAt: new Date(Date.now() - 1000 * 60 * 120).toISOString(),
    currency: null,
  },
  {
    id: "news-4",
    title: "US Non-Farm Payrolls due Friday — analysts expect 185K",
    source: "ForexFactory",
    impact: "HIGH" as const,
    publishedAt: new Date(Date.now() - 1000 * 60 * 180).toISOString(),
    currency: "USD",
  },
];

// ── Routes ───────────────────────────────────────────────────

router.get("/dashboard/status", async (req, res): Promise<void> => {
  req.log.info("Fetching dashboard status");

  const PYTHON_URL = process.env.PYTHON_AGENT_URL ?? "http://127.0.0.1:8000";
  const fetchPostgres = async (): Promise<{ connected: boolean; message: string; latencyMs: number | null }> => {
    if (!process.env.DATABASE_URL) {
      return { connected: false, message: "DATABASE_URL not set", latencyMs: null };
    }
    try {
      const t0 = Date.now();
      const r = await fetch(`${PYTHON_URL}/agents/health`, { signal: AbortSignal.timeout(2500) });
      const j = (await r.json()) as { services?: { postgres?: boolean } };
      const ok = !!j.services?.postgres;
      return {
        connected: ok,
        message: ok ? "PostgreSQL persistent store online" : "PostgreSQL not reachable",
        latencyMs: Date.now() - t0,
      };
    } catch (e) {
      return { connected: false, message: `health check failed: ${(e as Error).message}`, latencyMs: null };
    }
  };

  const [polygonStatus, redisStatus, postgresStatus] = await Promise.all([
    checkTwelveDataConnection(),
    checkRedisConnection(),
    fetchPostgres(),
  ]);

  const mt5Configured = !!(
    process.env.MT5_LOGIN &&
    process.env.MT5_PASSWORD &&
    process.env.MT5_SERVER
  );

  res.json({
    systemOnline: true,
    tradingState: TRADING_STATE,
    polygon: polygonStatus,
    redis: redisStatus,
    postgres: postgresStatus,
    mt5: {
      connected: mt5Configured,
      message: mt5Configured
        ? "MT5 credentials configured — Python bridge required to activate"
        : "MT5 not configured — set MT5_LOGIN, MT5_PASSWORD, MT5_SERVER",
      latencyMs: null,
    },
    account: {
      balance: demoBalance,
      equity: +(demoBalance * (1 - demoDailyDrawdown / 100)).toFixed(2),
      dailyDrawdownPct: demoDailyDrawdown,
      totalDrawdownPct: demoTotalDrawdown,
      dailyLimitPct: DAILY_LIMIT_PCT,
      totalLimitPct: TOTAL_LIMIT_PCT,
      currency: "USD",
    },
    lastUpdated: lastRefreshed,
  });
});

router.get("/dashboard/news", async (req, res): Promise<void> => {
  req.log.info("Fetching latest news");

  // Try Polygon first; fall back to static sample data
  const polygonNews = await fetchPolygonNews();

  if (polygonNews.length > 0) {
    const mapped = polygonNews.slice(0, 8).map((n) => ({
      id: n.id,
      title: n.title,
      source: n.source,
      impact: "MEDIUM" as const, // Polygon free tier doesn't return impact level
      publishedAt: n.publishedAt,
      currency: n.tickers[0]?.replace("X:", "") ?? null,
    }));
    res.json(mapped);
    return;
  }

  res.json(FALLBACK_NEWS);
});

router.get("/dashboard/agent-decisions", async (req, res): Promise<void> => {
  req.log.info("Fetching agent decisions");

  // Try to load cached decisions from Redis first
  const cached = await loadAgentDecisions<AgentDecision>();
  if (cached && cached.length > 0) {
    res.json(cached);
    return;
  }

  // If OpenAI is configured, run agents live
  if (isOpenAIConfigured()) {
    req.log.info("Running live AI agents");
    const [quotes, news] = await Promise.all([
      fetchTwelveDataQuotes(),
      fetchPolygonNews(),
    ]);

    const analysisDecision = await runAnalysisAgent(quotes, news);
    const riskDecision = await runRiskAgent(
      demoDailyDrawdown,
      demoTotalDrawdown,
      DAILY_LIMIT_PCT,
      TOTAL_LIMIT_PCT,
      analysisDecision.decision
    );
    const supervisorDecision = runSupervisorAgent(
      riskDecision.approved,
      TRADING_STATE
    );

    const dataAgentDecision: AgentDecision = {
      id: `dec-data-${Date.now()}`,
      agent: "Data Agent",
      decision: quotes.length > 0
        ? `ACTIVE — ${quotes.length} pairs loaded from Twelve Data`
        : "WAITING — Twelve Data API key required",
      reason: quotes.length > 0
        ? `Live quotes loaded: ${quotes.map((q) => q.symbol).join(", ")}.`
        : "Set TWELVE_DATA_API_KEY to enable real-time market data ingestion.",
      timestamp: new Date().toISOString(),
      approved: quotes.length > 0 ? true : null,
    };

    const decisions = [
      supervisorDecision,
      riskDecision,
      analysisDecision,
      dataAgentDecision,
    ];

    // Save to Redis for caching (5-min TTL)
    await saveAgentDecisions(decisions);
    await saveMarketSnapshot({ quotes, newsCount: news.length });

    res.json(decisions);
    return;
  }

  // Static fallback when nothing is configured
  res.json([
    {
      id: "dec-1",
      agent: "Supervisor Agent",
      decision: "HOLD — No trades allowed in Paper Mode",
      reason:
        "System is in PAPER_MODE. All signals are logged but not executed. Set OPENAI_API_KEY to enable AI agent decisions.",
      timestamp: new Date(Date.now() - 1000 * 60 * 5).toISOString(),
      approved: null,
    },
    {
      id: "dec-2",
      agent: "Risk Agent",
      decision: "MONITORING — Drawdown within safe limits",
      reason: `Daily drawdown ${demoDailyDrawdown}% below ${DAILY_LIMIT_PCT}% limit. Total drawdown ${demoTotalDrawdown}% below ${TOTAL_LIMIT_PCT}% limit.`,
      timestamp: new Date(Date.now() - 1000 * 60 * 10).toISOString(),
      approved: true,
    },
    {
      id: "dec-3",
      agent: "Analysis Agent",
      decision: "WAITING — OpenAI API key required",
      reason: "Set OPENAI_API_KEY to enable AI-powered market analysis and real trading signals.",
      timestamp: new Date(Date.now() - 1000 * 60 * 15).toISOString(),
      approved: null,
    },
    {
      id: "dec-4",
      agent: "Data Agent",
      decision: "WAITING — Twelve Data API key required",
      reason: "Set TWELVE_DATA_API_KEY to enable real-time forex data ingestion.",
      timestamp: new Date(Date.now() - 1000 * 60 * 20).toISOString(),
      approved: null,
    },
  ]);
});

// ── OHLC candles for Charts tab ──────────────────────────────────────────────
const VALID_SYMBOLS = new Set(["EURUSD", "GBPUSD", "USDJPY", "XAUUSD"]);

router.get("/ohlc/:symbol", async (req, res): Promise<void> => {
  const symbol = (req.params.symbol ?? "").toUpperCase();
  if (!VALID_SYMBOLS.has(symbol)) {
    res.status(400).json({ error: "Invalid symbol" });
    return;
  }
  req.log.info({ symbol }, "Fetching OHLC candles");
  const bars = await fetchTwelveDataOHLC(symbol, 15, "minute", 3);
  res.json({ symbol, source: bars.length > 0 ? "twelve_data" : "none", bars });
});

router.post("/dashboard/refresh", async (req, res): Promise<void> => {
  refreshCount++;
  lastRefreshed = new Date().toISOString();
  randomiseDemoValues(); // Simulate account change until MT5 connected

  logger.info({ refreshCount }, "Dashboard refresh triggered");
  res.json({
    success: true,
    message: `Data refreshed successfully (refresh #${refreshCount})`,
    timestamp: lastRefreshed,
  });
});

export default router;
