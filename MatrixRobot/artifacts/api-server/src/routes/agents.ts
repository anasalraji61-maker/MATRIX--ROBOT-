/**
 * /api/agents/* — thin proxy to the Python FastAPI agent service.
 *
 * Security layers:
 *   1. Python service requires X-Brain-Secret on all writes (fail-closed).
 *   2. This Node proxy adds X-Admin-Secret on write endpoints so external
 *      callers without the secret cannot trigger state changes.
 *
 * When the Python service is unavailable, returns graceful mock data
 * so the dashboard always has something to display.
 */
import { Router, type IRouter, type Request, type Response, type NextFunction } from "express";

const router: IRouter = Router();

const PYTHON_URL = process.env.PYTHON_AGENT_URL ?? "http://127.0.0.1:8000";
const PYTHON_URL_CONFIGURED = !!process.env.PYTHON_AGENT_URL;
const BRAIN_SECRET = process.env.MT5_BRIDGE_SECRET ?? "";

/** Host:port label for the brain target — never exposes paths/secrets. */
function targetHostLabel(): string {
  try {
    return new URL(PYTHON_URL).host;
  } catch {
    return "invalid-url";
  }
}

type FailureReason =
  | "timeout"
  | "refused"
  | "dns"
  | "reset"
  | "http_error"
  | "unknown";

/** Map a thrown fetch error to a coarse, user-actionable failure reason. */
function classifyFetchError(err: unknown): FailureReason {
  const e = err as { name?: string; code?: string; cause?: { code?: string } };
  const name = e?.name;
  const code = e?.code ?? e?.cause?.code;
  if (name === "TimeoutError" || code === "ETIMEDOUT") return "timeout";
  if (code === "ECONNREFUSED") return "refused";
  if (code === "ENOTFOUND" || code === "EAI_AGAIN") return "dns";
  if (code === "ECONNRESET") return "reset";
  return "unknown";
}

/** Human-readable, actionable message for a given failure reason. */
function reasonMessage(reason: FailureReason | null): string {
  const host = targetHostLabel();
  if (!PYTHON_URL_CONFIGURED) {
    return `PYTHON_AGENT_URL not set — defaulting to local ${host}, which is not running. Set PYTHON_AGENT_URL to your brain server.`;
  }
  switch (reason) {
    case "timeout":
      return `Brain server at ${host} did not respond in time (timeout) — the VPS may be down or unreachable.`;
    case "refused":
      return `Brain server at ${host} refused the connection — the brain service is not running on that host.`;
    case "dns":
      return `Brain server host ${host} could not be resolved — check PYTHON_AGENT_URL.`;
    case "reset":
      return `Connection to brain server at ${host} was reset — the VPS may be restarting or blocked by a firewall.`;
    case "http_error":
      return `Brain server at ${host} responded with an error.`;
    default:
      return `Brain server at ${host} is unreachable.`;
  }
}

// ── Admin secret guard (fail-closed) ──────────────────────────────────────
// Protects write (POST/DELETE) endpoints on the Node layer.
// Uses ADMIN_SECRET env var; falls back to MT5_BRIDGE_SECRET so no extra
// secret needs to be configured when MT5_BRIDGE_SECRET is already set.
// FAIL-CLOSED: if neither secret is configured, all write requests are
// rejected with 503 — this service must not be silently unprotected.
const ADMIN_SECRET = process.env.ADMIN_SECRET || process.env.MT5_BRIDGE_SECRET || "";

function requireAdminSecret(req: Request, res: Response, next: NextFunction): void {
  if (!ADMIN_SECRET) {
    // Fail-closed: no secret configured → reject all write requests.
    // Set ADMIN_SECRET (or MT5_BRIDGE_SECRET) in Replit Secrets to unlock.
    res.status(503).json({
      error: "Write operations disabled — ADMIN_SECRET not configured on server. " +
             "Set ADMIN_SECRET in Replit Secrets to enable write endpoints.",
    });
    return;
  }
  const provided = req.headers["x-admin-secret"] as string | undefined;
  if (!provided || provided !== ADMIN_SECRET) {
    res.status(401).json({ error: "Unauthorized — missing or invalid X-Admin-Secret header" });
    return;
  }
  next();
}

/** Headers for read-only (GET) proxy calls — no secret needed. */
const READ_HEADERS: Record<string, string> = {};

/** Headers for state-changing (POST/DELETE) proxy calls — include brain secret. */
function writeHeaders(): Record<string, string> {
  const h: Record<string, string> = { "Content-Type": "application/json" };
  if (BRAIN_SECRET) h["X-Brain-Secret"] = BRAIN_SECRET;
  return h;
}

async function proxyGet(
  path: string
): Promise<{ ok: boolean; data: unknown; reason?: FailureReason }> {
  try {
    const res = await fetch(`${PYTHON_URL}/agents${path}`, {
      headers: READ_HEADERS,
      signal: AbortSignal.timeout(5000),
    });
    if (!res.ok) return { ok: false, data: null, reason: "http_error" };
    return { ok: true, data: await res.json() };
  } catch (err) {
    return { ok: false, data: null, reason: classifyFetchError(err) };
  }
}

async function proxyPost(
  path: string,
  body: unknown
): Promise<{ ok: boolean; data: unknown }> {
  try {
    const res = await fetch(`${PYTHON_URL}/agents${path}`, {
      method: "POST",
      headers: writeHeaders(),
      body: JSON.stringify(body),
      signal: AbortSignal.timeout(10000),
    });
    const data = await res.json().catch(() => null);
    return { ok: res.ok, data };
  } catch {
    return { ok: false, data: null };
  }
}

async function proxyDelete(
  path: string
): Promise<{ ok: boolean; data: unknown }> {
  try {
    const res = await fetch(`${PYTHON_URL}/agents${path}`, {
      method: "DELETE",
      headers: writeHeaders(),
      signal: AbortSignal.timeout(5000),
    });
    if (!res.ok) return { ok: false, data: null };
    return { ok: true, data: await res.json() };
  } catch {
    return { ok: false, data: null };
  }
}

// ── Python service health / info ──────────────────────────────

router.get("/agents/status", async (req, res): Promise<void> => {
  req.log.info("Fetching Python agent service status");
  const [health, info] = await Promise.all([
    proxyGet("/health"),
    proxyGet("/info"),
  ]);

  if (!health.ok) {
    const reason = health.reason ?? "unknown";
    req.log.warn(
      { target: targetHostLabel(), configured: PYTHON_URL_CONFIGURED, reason },
      "Python agent service unreachable"
    );
    res.json({
      online: false,
      configured: PYTHON_URL_CONFIGURED,
      target: targetHostLabel(),
      reason,
      message: reasonMessage(reason),
      health: null,
      info: null,
    });
    return;
  }

  res.json({
    online: true,
    configured: PYTHON_URL_CONFIGURED,
    target: targetHostLabel(),
    health: health.data,
    info: info.data,
  });
});

// ── Trigger a new agent cycle ────────────────────────────────

router.post("/agents/cycle/run", requireAdminSecret, async (req, res): Promise<void> => {
  req.log.info("Triggering Python agent cycle");
  const { dry_run = true } = req.body ?? {};
  const result = await proxyPost("/cycle/run", { dry_run });

  if (!result.ok) {
    res.status(503).json({
      error: "Python agent service unavailable",
      detail: result.data,
    });
    return;
  }
  res.json(result.data);
});

// ── Get latest cycle status ──────────────────────────────────

router.get("/agents/cycle/status", async (req, res): Promise<void> => {
  req.log.info("Fetching agent cycle status");
  const result = await proxyGet("/cycle/status");

  if (!result.ok) {
    res.status(503).json({ error: "Python agent service unavailable" });
    return;
  }
  res.json(result.data);
});

// ── Latest signals ───────────────────────────────────────────

router.get("/agents/signals", async (req, res): Promise<void> => {
  req.log.info("Fetching latest agent signals");
  const result = await proxyGet("/signals");

  if (!result.ok) {
    res.status(503).json({ error: "No signals available" });
    return;
  }
  res.json(result.data);
});

// ── Agent state ──────────────────────────────────────────────

router.get("/agents/state", async (req, res): Promise<void> => {
  const result = await proxyGet("/state");
  if (!result.ok) {
    res.status(503).json({ error: "Python agent service unavailable" });
    return;
  }
  res.json(result.data);
});

// ── Trading mode switch ──────────────────────────────────────

router.get("/agents/mode", async (req, res): Promise<void> => {
  const result = await proxyGet("/mode");
  if (!result.ok) {
    res.status(503).json({ error: "Python agent service unavailable" });
    return;
  }
  res.json(result.data);
});

router.post("/agents/mode", requireAdminSecret, async (req, res): Promise<void> => {
  req.log.info(`Trading mode switch requested: ${JSON.stringify(req.body)}`);
  const result = await proxyPost("/mode", req.body);
  if (!result.ok) {
    res.status((result.data as any)?.detail ? 400 : 503).json(result.data ?? { error: "Failed to change mode" });
    return;
  }
  res.json(result.data);
});

// ── Auto-cycle scheduler ─────────────────────────────────────

router.get("/agents/scheduler/status", async (req, res): Promise<void> => {
  const result = await proxyGet("/scheduler/status");
  if (!result.ok) {
    res.status(503).json({ error: "Python agent service unavailable" });
    return;
  }
  res.json(result.data);
});

router.post("/agents/scheduler/start", requireAdminSecret, async (req, res): Promise<void> => {
  req.log.info("Starting auto-cycle scheduler");
  const { interval_minutes = 30 } = req.body ?? {};
  const result = await proxyPost("/scheduler/start", { interval_minutes });
  if (!result.ok) {
    res.status(503).json({ error: "Failed to start scheduler" });
    return;
  }
  res.json(result.data);
});

router.post("/agents/scheduler/stop", requireAdminSecret, async (req, res): Promise<void> => {
  req.log.info("Stopping auto-cycle scheduler");
  const result = await proxyPost("/scheduler/stop", {});
  if (!result.ok) {
    res.status(503).json({ error: "Failed to stop scheduler" });
    return;
  }
  res.json(result.data);
});

// ── FN compliance + analytics + execution variance ────────────

router.get("/agents/prop-status", async (req, res): Promise<void> => {
  const result = await proxyGet("/prop-status");
  if (!result.ok) {
    res.status(503).json({ error: "Python agent service unavailable" });
    return;
  }
  res.json(result.data);
});

router.get("/agents/analytics", async (req, res): Promise<void> => {
  const result = await proxyGet("/analytics");
  if (!result.ok) {
    res.status(503).json({ error: "Python agent service unavailable" });
    return;
  }
  res.json(result.data);
});

router.get("/agents/execution-variance", async (req, res): Promise<void> => {
  const result = await proxyGet("/execution-variance");
  if (!result.ok) {
    res.status(503).json({ error: "Python agent service unavailable" });
    return;
  }
  res.json(result.data);
});

// ── Live positions ────────────────────────────────────────────

router.get("/agents/positions/live", async (req, res): Promise<void> => {
  const result = await proxyGet("/positions/live");
  if (!result.ok) {
    res.status(503).json({ error: "Python agent service unavailable" });
    return;
  }
  res.json(result.data);
});

router.post("/agents/positions/:tradeId/close", requireAdminSecret, async (req, res): Promise<void> => {
  const { tradeId } = req.params;
  req.log.info(`Closing position: ${tradeId}`);
  const result = await proxyPost(`/positions/${tradeId}/close`, {});
  if (!result.ok) {
    res.status(503).json({ error: "Failed to close position" });
    return;
  }
  res.json(result.data);
});

// ── Multi-account ─────────────────────────────────────────────

router.get("/agents/accounts", async (req, res): Promise<void> => {
  const result = await proxyGet("/accounts");
  if (!result.ok) {
    res.status(503).json({ error: "Python agent service unavailable" });
    return;
  }
  res.json(result.data);
});

router.get("/agents/accounts/:accountId/positions", async (req, res): Promise<void> => {
  const { accountId } = req.params;
  const result = await proxyGet(`/accounts/${accountId}/positions`);
  if (!result.ok) {
    res.status(503).json({ error: "Python agent service unavailable" });
    return;
  }
  res.json(result.data);
});

router.get("/agents/pnl/summary", async (req, res): Promise<void> => {
  const result = await proxyGet("/pnl/summary");
  if (!result.ok) {
    res.json({ today_realized: 0, total_realized: 0, today_trades: 0, total_trades: 0, total_wins: 0, total_losses: 0, win_rate: null, best_trade: null, worst_trade: null, updated_at: new Date().toISOString() });
    return;
  }
  res.json(result.data);
});

router.get("/agents/strategy/scores", async (req, res): Promise<void> => {
  const window = req.query.window ? String(req.query.window) : undefined;
  const path = window ? `/strategy/scores?window=${window}` : "/strategy/scores";
  const result = await proxyGet(path);
  if (!result.ok) {
    res.json({ scores: [], dominant_strategy: null, window_trades: 50, updated_at: new Date().toISOString() });
    return;
  }
  res.json(result.data);
});

export default router;
