import { logger } from "../lib/logger";
import { fetchForexNews } from "./polygon";

export type SentimentLabel = "BULLISH" | "BEARISH" | "NEUTRAL";

export interface SentimentArticle {
  id: string;
  title: string;
  source: string;
  url: string;
  publishedAt: string;
  tickers: string[];
  sentiment: SentimentLabel;
  score: number;
  reasoning: string;
}

export interface SentimentReport {
  overallSentiment: SentimentLabel;
  overallScore: number;
  source: string;
  articles: SentimentArticle[];
  lastUpdated: string;
}

// ──────────────────────────────────────────────────────────
// GPT sentiment classifier via OpenRouter
// Sends all headlines in one batch call for efficiency
// ──────────────────────────────────────────────────────────

interface GptArticleSentiment {
  index: number;
  sentiment: SentimentLabel;
  score: number;
  reasoning: string;
}

async function classifyWithGPT(
  headlines: string[]
): Promise<GptArticleSentiment[]> {
  const orKey = process.env.OPENROUTER_API_KEY ?? "";
  const oaiKey = process.env.OPENAI_API_KEY ?? "";

  const apiKey = [orKey, oaiKey].find((k) => k.startsWith("sk-or-")) ??
    (orKey || oaiKey || "");

  if (!apiKey) {
    logger.warn("No LLM key available — returning neutral sentiment");
    return headlines.map((_, i) => ({
      index: i,
      sentiment: "NEUTRAL" as SentimentLabel,
      score: 0.5,
      reasoning: "No LLM key configured",
    }));
  }

  const isOpenRouter = apiKey.startsWith("sk-or-") || orKey;
  const baseURL = isOpenRouter
    ? "https://openrouter.ai/api/v1"
    : "https://api.openai.com/v1";

  const numbered = headlines
    .map((h, i) => `${i + 1}. "${h}"`)
    .join("\n");

  const prompt = `You are a quantitative analyst specializing in forex and commodity markets.
Classify each news headline below as BULLISH, BEARISH, or NEUTRAL for the broader financial market (USD, EUR, GBP, JPY, Gold).
For each headline return a JSON object with: index (0-based), sentiment (BULLISH|BEARISH|NEUTRAL), score (0.0-1.0 confidence), reasoning (max 10 words).
Return a JSON array only, no extra text.

Headlines:
${numbered}`;

  try {
    const res = await fetch(`${baseURL}/chat/completions`, {
      method: "POST",
      headers: {
        Authorization: `Bearer ${apiKey}`,
        "Content-Type": "application/json",
        ...(isOpenRouter && {
          "HTTP-Referer": "https://matrix-robot.replit.app",
          "X-Title": "Matrix Robot Trading Monitor",
        }),
      },
      body: JSON.stringify({
        model: "openai/gpt-4o-mini",
        messages: [{ role: "user", content: prompt }],
        temperature: 0.1,
        max_tokens: 600,
      }),
      signal: AbortSignal.timeout(15_000),
    });

    if (!res.ok) {
      const body = await res.text();
      logger.warn({ status: res.status, body }, "GPT sentiment API error");
      return fallbackSentiments(headlines);
    }

    const data = (await res.json()) as {
      choices: Array<{ message: { content: string } }>;
    };
    const content = data.choices?.[0]?.message?.content ?? "";

    const match = content.match(/\[[\s\S]*\]/);
    if (!match) {
      logger.warn({ content }, "GPT returned unexpected format");
      return fallbackSentiments(headlines);
    }

    const parsed = JSON.parse(match[0]) as GptArticleSentiment[];
    return parsed.map((p) => ({
      index: p.index,
      sentiment: (["BULLISH", "BEARISH", "NEUTRAL"].includes(p.sentiment)
        ? p.sentiment
        : "NEUTRAL") as SentimentLabel,
      score: Math.max(0, Math.min(1, Number(p.score) || 0.5)),
      reasoning: String(p.reasoning ?? "").slice(0, 120),
    }));
  } catch (err) {
    logger.error({ err }, "GPT sentiment classification failed");
    return fallbackSentiments(headlines);
  }
}

function fallbackSentiments(headlines: string[]): GptArticleSentiment[] {
  return headlines.map((_, i) => ({
    index: i,
    sentiment: "NEUTRAL" as SentimentLabel,
    score: 0.5,
    reasoning: "Analysis unavailable",
  }));
}

// ──────────────────────────────────────────────────────────
// Demo articles when Polygon is not configured
// ──────────────────────────────────────────────────────────

function demoArticles(): SentimentArticle[] {
  return [
    {
      id: "demo-1",
      title: "Fed holds rates steady, signals patience on cuts",
      source: "Reuters",
      url: "#",
      publishedAt: new Date(Date.now() - 1000 * 60 * 15).toISOString(),
      tickers: ["C:EURUSD", "C:USDJPY"],
      sentiment: "NEUTRAL",
      score: 0.62,
      reasoning: "Rate hold was expected, no new guidance",
    },
    {
      id: "demo-2",
      title: "EUR/USD consolidates ahead of ECB minutes",
      source: "Bloomberg",
      url: "#",
      publishedAt: new Date(Date.now() - 1000 * 60 * 40).toISOString(),
      tickers: ["C:EURUSD"],
      sentiment: "NEUTRAL",
      score: 0.55,
      reasoning: "Awaiting catalyst, range-bound",
    },
    {
      id: "demo-3",
      title: "Gold edges higher as dollar weakens on soft CPI",
      source: "MarketWatch",
      url: "#",
      publishedAt: new Date(Date.now() - 1000 * 60 * 70).toISOString(),
      tickers: ["C:XAUUSD"],
      sentiment: "BULLISH",
      score: 0.74,
      reasoning: "Soft inflation supports gold and risk assets",
    },
    {
      id: "demo-4",
      title: "US Non-Farm Payrolls beat estimates at 215K",
      source: "CNBC",
      url: "#",
      publishedAt: new Date(Date.now() - 1000 * 60 * 120).toISOString(),
      tickers: ["C:EURUSD", "C:GBPUSD"],
      sentiment: "BEARISH",
      score: 0.68,
      reasoning: "Strong jobs data supports USD strength",
    },
  ];
}

// ──────────────────────────────────────────────────────────
// Main report builder
// ──────────────────────────────────────────────────────────

export async function buildSentimentReport(): Promise<SentimentReport> {
  const polygonKey = process.env.POLYGON_API_KEY;
  const hasLLM = !!(
    process.env.OPENROUTER_API_KEY ||
    process.env.OPENAI_API_KEY
  );

  if (!polygonKey || !hasLLM) {
    logger.warn(
      { hasPolygon: !!polygonKey, hasLLM },
      "Using demo sentiment — configure POLYGON_API_KEY and OpenRouter/OpenAI key"
    );
    const articles = demoArticles();
    return {
      overallSentiment: "NEUTRAL",
      overallScore: 0,
      source: "demo",
      articles,
      lastUpdated: new Date().toISOString(),
    };
  }

  const news = await fetchForexNews();

  if (news.length === 0) {
    logger.warn("No Polygon news returned — using demo sentiment");
    const articles = demoArticles();
    return {
      overallSentiment: "NEUTRAL",
      overallScore: 0,
      source: "demo",
      articles,
      lastUpdated: new Date().toISOString(),
    };
  }

  const headlines = news.map((n) => n.title);
  const classifications = await classifyWithGPT(headlines);

  const classMap = new Map(classifications.map((c) => [c.index, c]));
  const scoreMap: Record<SentimentLabel, number> = {
    BULLISH: 1,
    BEARISH: -1,
    NEUTRAL: 0,
  };

  const articles: SentimentArticle[] = news.map((n, i) => {
    const cls = classMap.get(i) ?? {
      sentiment: "NEUTRAL" as SentimentLabel,
      score: 0.5,
      reasoning: "Not classified",
    };
    return {
      id: n.id,
      title: n.title,
      source: n.source,
      url: n.url,
      publishedAt: n.publishedAt,
      tickers: n.tickers,
      sentiment: cls.sentiment,
      score: cls.score,
      reasoning: cls.reasoning,
    };
  });

  const scores = articles.map((a) => scoreMap[a.sentiment] * a.score);
  const overallScore =
    scores.length > 0
      ? +(scores.reduce((a, b) => a + b, 0) / scores.length).toFixed(4)
      : 0;

  const overallSentiment: SentimentLabel =
    overallScore > 0.15 ? "BULLISH" : overallScore < -0.15 ? "BEARISH" : "NEUTRAL";

  logger.info(
    { articles: articles.length, overallSentiment, overallScore },
    "Sentiment report built from Polygon + GPT"
  );

  return {
    overallSentiment,
    overallScore,
    source: "polygon-news+gpt",
    articles,
    lastUpdated: new Date().toISOString(),
  };
}
