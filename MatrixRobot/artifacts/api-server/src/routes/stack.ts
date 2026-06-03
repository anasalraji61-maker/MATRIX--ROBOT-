import { Router, type IRouter } from "express";

const router: IRouter = Router();

function env(...keys: string[]): boolean {
  return keys.every((k) => !!process.env[k]);
}

function partial(...keys: string[]): boolean {
  return keys.some((k) => !!process.env[k]) && !keys.every((k) => !!process.env[k]);
}

function buildStack() {
  const services = [
    // ── Trading Execution ─────────────────────────────────────────────────
    {
      id: "mt5",
      name: "MetaTrader 5",
      category: "Trading",
      description: "Trade execution & account management via Python MT5 bridge",
      configured: env("MT5_LOGIN", "MT5_PASSWORD", "MT5_SERVER"),
      status: env("MT5_LOGIN", "MT5_PASSWORD", "MT5_SERVER")
        ? "configured"
        : partial("MT5_LOGIN", "MT5_PASSWORD", "MT5_SERVER")
        ? "partial"
        : "missing",
      setupHint: "Set MT5_LOGIN, MT5_PASSWORD, MT5_SERVER",
    },

    // ── Market Data ───────────────────────────────────────────────────────
    {
      id: "twelve_data",
      name: "Twelve Data",
      category: "Market Data",
      description: "Primary market data — real-time forex quotes & OHLC (Grow plan, 55 req/min)",
      configured: env("TWELVE_DATA_API_KEY"),
      status: env("TWELVE_DATA_API_KEY") ? "active" : "missing",
      setupHint: "Set TWELVE_DATA_API_KEY (twelvedata.com)",
    },
    {
      id: "polygon",
      name: "Polygon.io",
      category: "Market Data",
      description: "Legacy news source — used only by sentiment route (Grow plan lacks news)",
      configured: env("POLYGON_API_KEY"),
      status: env("POLYGON_API_KEY") ? "active" : "missing",
      setupHint: "Set POLYGON_API_KEY (free at polygon.io)",
    },

    // ── LLM / AI ─────────────────────────────────────────────────────────
    {
      id: "openrouter",
      name: "OpenRouter",
      category: "LLM / AI",
      description: "LLM gateway — routes agent requests to the best available model",
      configured: env("OPENROUTER_API_KEY"),
      status: env("OPENROUTER_API_KEY") ? "active" : "missing",
      setupHint: "Set OPENROUTER_API_KEY (openrouter.ai)",
    },
    {
      id: "openai",
      name: "OpenAI",
      category: "LLM / AI",
      description: "GPT-4o-mini powers Analysis Agent and Risk Agent decisions",
      configured: env("OPENAI_API_KEY"),
      status: env("OPENAI_API_KEY") ? "active" : "missing",
      setupHint: "Set OPENAI_API_KEY (platform.openai.com)",
    },
    {
      id: "finbert",
      name: "FinBERT (HuggingFace)",
      category: "LLM / AI",
      description: "Financial BERT model for news sentiment classification",
      configured: env("HUGGINGFACE_API_KEY"),
      status: env("HUGGINGFACE_API_KEY") ? "active" : "missing",
      setupHint: "Set HUGGINGFACE_API_KEY (free at huggingface.co)",
    },

    // ── AI Agents ─────────────────────────────────────────────────────────
    {
      id: "langchain",
      name: "LangChain",
      category: "Agent Framework",
      description: "Orchestration framework for multi-agent pipelines",
      configured: env("PYTHON_AGENT_URL"),
      status: env("PYTHON_AGENT_URL") ? "active" : "missing",
      setupHint: "Set PYTHON_AGENT_URL when Python bridge is deployed",
    },
    {
      id: "fastapi",
      name: "FastAPI",
      category: "Agent Framework",
      description: "Python micro-service exposing agent endpoints to this server",
      configured: env("PYTHON_AGENT_URL"),
      status: env("PYTHON_AGENT_URL") ? "active" : "missing",
      setupHint: "Set PYTHON_AGENT_URL (e.g. http://127.0.0.1:8000)",
    },
    {
      id: "python-agents",
      name: "Python Agents",
      category: "Agent Framework",
      description: "Supervisor, Analysis, Risk and Data agents running in Python",
      configured: env("PYTHON_AGENT_URL"),
      status: env("PYTHON_AGENT_URL") ? "active" : "missing",
      setupHint: "Deploy the Python agent service and set PYTHON_AGENT_URL",
    },

    // ── Sentiment / Social ────────────────────────────────────────────────
    {
      id: "brand24",
      name: "Brand24",
      category: "Sentiment",
      description: "Social media monitoring — tracks forex & market sentiment mentions",
      configured: env("BRAND24_API_KEY", "BRAND24_PROJECT_ID"),
      status: env("BRAND24_API_KEY", "BRAND24_PROJECT_ID")
        ? "active"
        : partial("BRAND24_API_KEY", "BRAND24_PROJECT_ID")
        ? "partial"
        : "missing",
      setupHint: "Set BRAND24_API_KEY + BRAND24_PROJECT_ID (brand24.com)",
    },

    // ── Memory / Database ─────────────────────────────────────────────────
    {
      id: "redis",
      name: "Redis",
      category: "Memory / Storage",
      description: "Agent short-term memory — caches decisions and market snapshots",
      configured: env("REDIS_URL"),
      status: env("REDIS_URL") ? "active" : "missing",
      setupHint: "Set REDIS_URL (free tier at upstash.com)",
    },
    {
      id: "supabase",
      name: "Supabase",
      category: "Memory / Storage",
      description: "Managed PostgreSQL — stores trade history, agent logs, and configs",
      configured: env("DATABASE_URL") || env("SUPABASE_URL"),
      status: env("DATABASE_URL") || env("SUPABASE_URL") ? "active" : "missing",
      setupHint: "Set DATABASE_URL or SUPABASE_URL (supabase.com free tier)",
    },
    {
      id: "postgres",
      name: "PostgreSQL",
      category: "Memory / Storage",
      description: "Relational database powering Supabase and Drizzle ORM",
      configured: env("DATABASE_URL"),
      status: env("DATABASE_URL") ? "active" : "missing",
      setupHint: "Set DATABASE_URL (included with Supabase)",
    },
    {
      id: "pgvector",
      name: "PGVector",
      category: "Memory / Storage",
      description: "Vector store extension for semantic search and agent embeddings",
      configured: env("DATABASE_URL"),
      status: env("DATABASE_URL") ? "configured" : "missing",
      setupHint: "Enabled via pgvector extension on PostgreSQL — needs DATABASE_URL",
    },
  ] as const;

  const categories = [...new Set(services.map((s) => s.category))];
  const configuredCount = services.filter((s) => s.configured).length;

  return {
    services,
    totalCount: services.length,
    configuredCount,
    categories,
  };
}

router.get("/stack", (req, res): void => {
  req.log.info("Fetching system stack status");
  res.json(buildStack());
});

export default router;
