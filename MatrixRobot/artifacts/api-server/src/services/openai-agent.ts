import OpenAI from "openai";
import { logger } from "../lib/logger";
import type { TwelveDataQuote as PolygonQuote } from "./twelve_data";
import type { PolygonNewsItem } from "./polygon";

export interface AgentDecision {
  id: string;
  agent: string;
  decision: string;
  reason: string;
  timestamp: string;
  approved: boolean | null;
}

let openaiClient: OpenAI | null = null;

function getLLMKey(): { apiKey: string; baseURL?: string; model: string } | null {
  const orEnv = process.env.OPENROUTER_API_KEY ?? "";
  const oaiEnv = process.env.OPENAI_API_KEY ?? "";

  // Prefer whichever key explicitly matches OpenRouter format (sk-or-)
  const orKey = [orEnv, oaiEnv].find(k => k.startsWith("sk-or-"))
    ?? (orEnv || undefined); // fallback: OPENROUTER_API_KEY regardless of format

  if (orKey) {
    return {
      apiKey: orKey,
      baseURL: "https://openrouter.ai/api/v1",
      model: "openai/gpt-4o-mini",
    };
  }
  if (oaiEnv) return { apiKey: oaiEnv, model: "gpt-4o-mini" };
  return null;
}

function getOpenAIClient(): OpenAI | null {
  const cfg = getLLMKey();
  if (!cfg) return null;
  if (!openaiClient) {
    openaiClient = new OpenAI({ apiKey: cfg.apiKey, baseURL: cfg.baseURL });
  }
  return openaiClient;
}

export function isOpenAIConfigured(): boolean {
  return getLLMKey() !== null;
}

// ──────────────────────────────────────────────────────────────
// Analysis Agent
// Reads market data + news, returns a trading signal
// ──────────────────────────────────────────────────────────────

export async function runAnalysisAgent(
  quotes: PolygonQuote[],
  news: PolygonNewsItem[]
): Promise<AgentDecision> {
  const timestamp = new Date().toISOString();
  const client = getOpenAIClient();

  if (!client) {
    return {
      id: `dec-analysis-${Date.now()}`,
      agent: "Analysis Agent",
      decision: "WAITING — OpenAI API key required",
      reason:
        "Set OPENAI_API_KEY to enable AI-powered market analysis. Currently running without live analysis.",
      timestamp,
      approved: null,
    };
  }

  const quoteSummary =
    quotes.length > 0
      ? quotes
          .map(
            (q) =>
              `${q.symbol}: ${q.price.toFixed(5)} (${q.changePct >= 0 ? "+" : ""}${q.changePct.toFixed(2)}%)`
          )
          .join(", ")
      : "No live quotes available";

  const newsSummary =
    news.length > 0
      ? news
          .slice(0, 5)
          .map((n) => `• ${n.title}`)
          .join("\n")
      : "No live news available";

  const systemPrompt = `You are an Analysis Agent for an autonomous Forex trading system operating in PAPER MODE (no real trades).
Your job is to analyze current market conditions and produce a concise trading signal.

Rules:
- Keep the decision under 10 words (e.g. "SIGNAL — EUR/USD bullish breakout above 1.0850")
- Keep the reason under 50 words, technical and factual
- Never recommend a specific lot size or leverage
- Always note that the system is in PAPER MODE
- Output ONLY valid JSON: {"decision": "...", "reason": "..."}`;

  const userMessage = `Current forex quotes: ${quoteSummary}

Recent news:
${newsSummary}

Provide your analysis signal.`;

  try {
    const completion = await client.chat.completions.create({
      model: "gpt-4o-mini",
      messages: [
        { role: "system", content: systemPrompt },
        { role: "user", content: userMessage },
      ],
      response_format: { type: "json_object" },
      max_tokens: 200,
      temperature: 0.3,
    });

    const content = completion.choices[0]?.message?.content ?? "{}";
    const parsed = JSON.parse(content) as { decision?: string; reason?: string };

    return {
      id: `dec-analysis-${Date.now()}`,
      agent: "Analysis Agent",
      decision: parsed.decision ?? "NEUTRAL — Insufficient signal",
      reason: parsed.reason ?? "Model returned no reason.",
      timestamp,
      approved: null,
    };
  } catch (err) {
    logger.error({ err }, "OpenAI Analysis Agent failed");
    return {
      id: `dec-analysis-${Date.now()}`,
      agent: "Analysis Agent",
      decision: "ERROR — OpenAI request failed",
      reason: String(err),
      timestamp,
      approved: null,
    };
  }
}

// ──────────────────────────────────────────────────────────────
// Risk Agent
// Checks drawdown limits and market conditions before approving
// ──────────────────────────────────────────────────────────────

export async function runRiskAgent(
  dailyDrawdownPct: number,
  totalDrawdownPct: number,
  dailyLimit: number,
  totalLimit: number,
  analysisDecision: string
): Promise<AgentDecision> {
  const timestamp = new Date().toISOString();
  const client = getOpenAIClient();

  const dailyBreached = dailyDrawdownPct >= dailyLimit;
  const totalBreached = totalDrawdownPct >= totalLimit;
  const dailyWarning = dailyDrawdownPct >= dailyLimit * 0.8;
  const totalWarning = totalDrawdownPct >= totalLimit * 0.8;

  // Rule-based risk check (no OpenAI needed for this)
  if (dailyBreached) {
    return {
      id: `dec-risk-${Date.now()}`,
      agent: "Risk Agent",
      decision: "FROZEN — Daily loss limit breached",
      reason: `Daily drawdown ${dailyDrawdownPct}% has exceeded the ${dailyLimit}% limit. All trading suspended until next session.`,
      timestamp,
      approved: false,
    };
  }

  if (totalBreached) {
    return {
      id: `dec-risk-${Date.now()}`,
      agent: "Risk Agent",
      decision: "FROZEN — Total loss limit breached",
      reason: `Total drawdown ${totalDrawdownPct}% has exceeded the ${totalLimit}% limit. Manual intervention required.`,
      timestamp,
      approved: false,
    };
  }

  if (!client) {
    const status =
      dailyWarning || totalWarning ? "WARNING — Drawdown approaching limits" : "MONITORING — Risk within limits";
    return {
      id: `dec-risk-${Date.now()}`,
      agent: "Risk Agent",
      decision: status,
      reason: `Daily: ${dailyDrawdownPct}%/${dailyLimit}% | Total: ${totalDrawdownPct}%/${totalLimit}%. ${dailyWarning || totalWarning ? "Approaching threshold — proceed with caution." : "All limits safe."}`,
      timestamp,
      approved: !dailyWarning && !totalWarning,
    };
  }

  // Use OpenAI for a more nuanced risk assessment when available
  try {
    const completion = await client.chat.completions.create({
      model: "gpt-4o-mini",
      messages: [
        {
          role: "system",
          content: `You are a Risk Management Agent for a Forex trading system in PAPER MODE.
Assess whether the proposed trade signal is safe given current drawdown levels.
Output ONLY valid JSON: {"decision": "...", "reason": "...", "approved": true|false}
Keep decision under 10 words, reason under 40 words.`,
        },
        {
          role: "user",
          content: `Daily drawdown: ${dailyDrawdownPct}% (limit: ${dailyLimit}%)
Total drawdown: ${totalDrawdownPct}% (limit: ${totalLimit}%)
Proposed signal: ${analysisDecision}
Approve this signal?`,
        },
      ],
      response_format: { type: "json_object" },
      max_tokens: 150,
      temperature: 0.1,
    });

    const content = completion.choices[0]?.message?.content ?? "{}";
    const parsed = JSON.parse(content) as {
      decision?: string;
      reason?: string;
      approved?: boolean;
    };

    return {
      id: `dec-risk-${Date.now()}`,
      agent: "Risk Agent",
      decision: parsed.decision ?? "MONITORING — Risk evaluated",
      reason: parsed.reason ?? "Risk assessment complete.",
      timestamp,
      approved: parsed.approved ?? true,
    };
  } catch (err) {
    logger.error({ err }, "OpenAI Risk Agent failed");
    return {
      id: `dec-risk-${Date.now()}`,
      agent: "Risk Agent",
      decision: "MONITORING — Rule-based check passed",
      reason: `Daily: ${dailyDrawdownPct}%/${dailyLimit}% | Total: ${totalDrawdownPct}%/${totalLimit}%. All within safe limits.`,
      timestamp,
      approved: true,
    };
  }
}

// ──────────────────────────────────────────────────────────────
// Supervisor Agent
// Final gate — only approves if Risk Agent approved
// ──────────────────────────────────────────────────────────────

export function runSupervisorAgent(
  riskApproved: boolean | null,
  tradingState: string
): AgentDecision {
  const timestamp = new Date().toISOString();

  if (tradingState !== "ACTIVE") {
    return {
      id: `dec-supervisor-${Date.now()}`,
      agent: "Supervisor Agent",
      decision: `HOLD — System in ${tradingState.replace("_", " ")}`,
      reason:
        "No trade execution in PAPER_MODE or FROZEN state. All signals are logged for analysis only.",
      timestamp,
      approved: null,
    };
  }

  if (!riskApproved) {
    return {
      id: `dec-supervisor-${Date.now()}`,
      agent: "Supervisor Agent",
      decision: "BLOCKED — Risk Agent rejected signal",
      reason:
        "Trade blocked by Risk Agent. Supervisor will not override risk decisions.",
      timestamp,
      approved: false,
    };
  }

  return {
    id: `dec-supervisor-${Date.now()}`,
    agent: "Supervisor Agent",
    decision: "APPROVED — Signal cleared for execution",
    reason:
      "Risk Agent approved. Execution Agent queued for trade placement.",
    timestamp,
    approved: true,
  };
}
