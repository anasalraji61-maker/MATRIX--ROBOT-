import { Router, type IRouter } from "express";
import path from "path";
import fs from "fs";

const router: IRouter = Router();

const BRIDGE_DIR = path.resolve(
  __dirname,
  "../../python-agents"
);

const EXPORTS_DIR = path.resolve(__dirname, "../../../exports");

router.get("/download/mt5-bridge", (_req, res) => {
  const file = path.join(BRIDGE_DIR, "mt5_windows_bridge.py");
  if (!fs.existsSync(file)) {
    res.status(404).json({ error: "File not found" });
    return;
  }
  res.setHeader("Content-Disposition", 'attachment; filename="mt5_windows_bridge.py"');
  res.setHeader("Content-Type", "text/plain; charset=utf-8");
  res.sendFile(file);
});

router.get("/download/mt5-bat", (_req, res) => {
  const file = path.join(BRIDGE_DIR, "START_MT5_BRIDGE.bat");
  if (!fs.existsSync(file)) {
    res.status(404).json({ error: "File not found" });
    return;
  }
  res.setHeader("Content-Disposition", 'attachment; filename="START_MT5_BRIDGE.bat"');
  res.setHeader("Content-Type", "application/octet-stream");
  res.sendFile(file);
});

router.get("/download/mt5-start-all", (_req, res) => {
  const file = path.join(BRIDGE_DIR, "START_ALL.bat");
  if (!fs.existsSync(file)) {
    res.status(404).json({ error: "File not found" });
    return;
  }
  res.setHeader("Content-Disposition", 'attachment; filename="START_ALL.bat"');
  res.setHeader("Content-Type", "application/octet-stream");
  res.sendFile(file);
});

router.get("/download/mt5-bat-ngrok", (_req, res) => {
  const file = path.join(BRIDGE_DIR, "START_MT5_BRIDGE_NGROK.bat");
  if (!fs.existsSync(file)) {
    res.status(404).json({ error: "File not found" });
    return;
  }
  res.setHeader("Content-Disposition", 'attachment; filename="START_MT5_BRIDGE_NGROK.bat"');
  res.setHeader("Content-Type", "application/octet-stream");
  res.sendFile(file);
});

router.get("/download/mt5-bat-vps", (_req, res) => {
  const file = path.join(BRIDGE_DIR, "START_MT5_BRIDGE_VPS.bat");
  if (!fs.existsSync(file)) {
    res.status(404).json({ error: "File not found" });
    return;
  }
  res.setHeader("Content-Disposition", 'attachment; filename="START_MT5_BRIDGE_VPS.bat"');
  res.setHeader("Content-Type", "application/octet-stream");
  res.sendFile(file);
});

router.get("/download/mt5-bat-bore", (_req, res) => {
  const file = path.join(BRIDGE_DIR, "START_MT5_BRIDGE_BORE.bat");
  if (!fs.existsSync(file)) {
    res.status(404).json({ error: "File not found" });
    return;
  }
  res.setHeader("Content-Disposition", 'attachment; filename="START_MT5_BRIDGE_BORE.bat"');
  res.setHeader("Content-Type", "application/octet-stream");
  res.sendFile(file);
});

router.get("/download/mt5-bat-forexiraq", (_req, res) => {
  const file = path.join(BRIDGE_DIR, "START_MT5_BRIDGE_FOREXIRAQ.bat");
  if (!fs.existsSync(file)) {
    res.status(404).json({ error: "File not found" });
    return;
  }
  res.setHeader("Content-Disposition", 'attachment; filename="START_MT5_BRIDGE_FOREXIRAQ.bat"');
  res.setHeader("Content-Type", "application/octet-stream");
  res.sendFile(file);
});

// NOTE: Download routes serve TEMPLATE files only — no real secrets are
// embedded. Fill in your actual values after downloading.
router.get("/download/mt5-env", (_req, res) => {
  const server = process.env["MT5_SERVER"] ?? "MetaQuotes-Demo";
  const content = [
    "# MT5 Bridge .env — fill in your credentials",
    `MT5_LOGIN=YOUR_MT5_LOGIN`,
    `MT5_PASSWORD=YOUR_MT5_PASSWORD`,
    `MT5_SERVER=${server}`,
    `MT5_BRIDGE_SECRET=YOUR_BRIDGE_SECRET`,
    "",
  ].join("\n");
  res.setHeader("Content-Disposition", 'attachment; filename=".env"');
  res.setHeader("Content-Type", "text/plain; charset=utf-8");
  res.send(content);
});

// Pre-filled .env template for the BRAIN on the VPS.
// SECURITY: uses placeholder values — never embeds real API keys.
// Copy your actual keys from Replit Secrets after downloading.
router.get("/download/brain-env", (_req, res) => {
  const lines = [
    "# Matrix Robot - BRAIN .env (place next to START_BRAIN.bat)",
    "# Fill in your actual values — see Replit Secrets for the real keys.",
    "",
    "# Bridge on same VPS:",
    "MT5_BRIDGE_URL=http://127.0.0.1:5555",
    "MT5_BRIDGE_SECRET=YOUR_BRIDGE_SECRET",
    "",
    "# LLM keys — copy from Replit Secrets",
    "GOOGLE_API_KEY=YOUR_GOOGLE_API_KEY",
    "GEMINI_API_KEY=YOUR_GEMINI_API_KEY",
    "OPENROUTER_API_KEY=YOUR_OPENROUTER_API_KEY",
    "OPENAI_API_KEY=YOUR_OPENAI_API_KEY",
    "",
    "# Market data — copy from Replit Secrets",
    "TWELVE_DATA_API_KEY=YOUR_TWELVE_DATA_KEY",
    "POLYGON_API_KEY=YOUR_POLYGON_KEY",
    "",
    "# MT5 account — copy from Replit Secrets",
    "MT5_LOGIN=YOUR_MT5_LOGIN",
    "MT5_PASSWORD=YOUR_MT5_PASSWORD",
    "MT5_SERVER=YOUR_MT5_SERVER",
    "",
    "# Safety defaults — do NOT change until ready",
    "TRADING_STATE=PAPER_MODE",
    "ALLOW_LIVE_TRADING=false",
    "",
  ];
  res.setHeader("Content-Disposition", 'attachment; filename=".env"');
  res.setHeader("Content-Type", "text/plain; charset=utf-8");
  res.send(lines.join("\n"));
});

// Full brain code package (zip) for the VPS. Pre-built into exports/.
router.get("/download/brain-package", (_req, res) => {
  const file = path.join(EXPORTS_DIR, "matrix-brain.zip");
  if (!fs.existsSync(file)) {
    res.status(404).json({ error: "Package not built yet" });
    return;
  }
  res.setHeader("Content-Disposition", 'attachment; filename="matrix-brain.zip"');
  res.setHeader("Content-Type", "application/zip");
  res.sendFile(file);
});

router.get("/download/tools-pdf", (_req, res) => {
  const file = path.join(EXPORTS_DIR, "matrix-robot-tools.pdf");
  if (!fs.existsSync(file)) {
    res.status(404).json({ error: "File not found" });
    return;
  }
  res.setHeader("Content-Disposition", 'inline; filename="matrix-robot-tools.pdf"');
  res.setHeader("Content-Type", "application/pdf");
  res.sendFile(file);
});

router.get("/download/brain-agentic", (_req, res) => {
  const file = path.join(BRIDGE_DIR, "agents", "agentic_brain.py");
  if (!fs.existsSync(file)) {
    res.status(404).json({ error: "File not found" });
    return;
  }
  res.setHeader("Content-Disposition", 'attachment; filename="agentic_brain.py"');
  res.setHeader("Content-Type", "text/plain; charset=utf-8");
  res.sendFile(file);
});

router.get("/download/brain-health", (_req, res) => {
  const file = path.join(BRIDGE_DIR, "routes", "health.py");
  if (!fs.existsSync(file)) {
    res.status(404).json({ error: "File not found" });
    return;
  }
  res.setHeader("Content-Disposition", 'attachment; filename="health.py"');
  res.setHeader("Content-Type", "text/plain; charset=utf-8");
  res.sendFile(file);
});

router.get("/download/brain-main", (_req, res) => {
  const file = path.join(BRIDGE_DIR, "main.py");
  if (!fs.existsSync(file)) {
    res.status(404).json({ error: "File not found" });
    return;
  }
  res.setHeader("Content-Disposition", 'attachment; filename="main.py"');
  res.setHeader("Content-Type", "text/plain; charset=utf-8");
  res.sendFile(file);
});

router.get("/download/brain-usage-route", (_req, res) => {
  const file = path.join(BRIDGE_DIR, "routes", "usage.py");
  if (!fs.existsSync(file)) {
    res.status(404).json({ error: "File not found" });
    return;
  }
  res.setHeader("Content-Disposition", 'attachment; filename="usage.py"');
  res.setHeader("Content-Type", "text/plain; charset=utf-8");
  res.sendFile(file);
});

router.get("/download/brain-mt5-bridge", (_req, res) => {
  const file = path.join(BRIDGE_DIR, "tools", "mt5_bridge.py");
  if (!fs.existsSync(file)) {
    res.status(404).json({ error: "File not found" });
    return;
  }
  res.setHeader("Content-Disposition", 'attachment; filename="mt5_bridge.py"');
  res.setHeader("Content-Type", "text/plain; charset=utf-8");
  res.sendFile(file);
});

router.get("/download/brain-execution-variance", (_req, res) => {
  const file = path.join(BRIDGE_DIR, "tools", "execution_variance.py");
  if (!fs.existsSync(file)) {
    res.status(404).json({ error: "File not found" });
    return;
  }
  res.setHeader("Content-Disposition", 'attachment; filename="execution_variance.py"');
  res.setHeader("Content-Type", "text/plain; charset=utf-8");
  res.sendFile(file);
});

router.get("/download/brain-trading-route", (_req, res) => {
  const file = path.join(BRIDGE_DIR, "routes", "trading.py");
  if (!fs.existsSync(file)) {
    res.status(404).json({ error: "File not found" });
    return;
  }
  res.setHeader("Content-Disposition", 'attachment; filename="trading.py"');
  res.setHeader("Content-Type", "text/plain; charset=utf-8");
  res.sendFile(file);
});

router.get("/download/brain-config", (_req, res) => {
  const file = path.join(BRIDGE_DIR, "config.py");
  if (!fs.existsSync(file)) {
    res.status(404).json({ error: "File not found" });
    return;
  }
  res.setHeader("Content-Disposition", 'attachment; filename="config.py"');
  res.setHeader("Content-Type", "text/plain; charset=utf-8");
  res.sendFile(file);
});

// ── APE (Adaptive Policy Envelope) update routes ────────────────
router.get("/download/brain-adaptive-policy", (_req, res) => {
  const file = path.join(BRIDGE_DIR, "tools", "adaptive_policy.py");
  if (!fs.existsSync(file)) {
    res.status(404).json({ error: "File not found" });
    return;
  }
  res.setHeader("Content-Disposition", 'attachment; filename="adaptive_policy.py"');
  res.setHeader("Content-Type", "text/plain; charset=utf-8");
  res.sendFile(file);
});

router.get("/download/brain-registry", (_req, res) => {
  const file = path.join(BRIDGE_DIR, "tools", "registry.py");
  if (!fs.existsSync(file)) {
    res.status(404).json({ error: "File not found" });
    return;
  }
  res.setHeader("Content-Disposition", 'attachment; filename="registry.py"');
  res.setHeader("Content-Type", "text/plain; charset=utf-8");
  res.sendFile(file);
});

router.get("/download/brain-risk-agent", (_req, res) => {
  const file = path.join(BRIDGE_DIR, "agents", "risk_agent.py");
  if (!fs.existsSync(file)) {
    res.status(404).json({ error: "File not found" });
    return;
  }
  res.setHeader("Content-Disposition", 'attachment; filename="risk_agent.py"');
  res.setHeader("Content-Type", "text/plain; charset=utf-8");
  res.sendFile(file);
});

router.get("/download/brain-state-route", (_req, res) => {
  const file = path.join(BRIDGE_DIR, "routes", "state.py");
  if (!fs.existsSync(file)) {
    res.status(404).json({ error: "File not found" });
    return;
  }
  res.setHeader("Content-Disposition", 'attachment; filename="state.py"');
  res.setHeader("Content-Type", "text/plain; charset=utf-8");
  res.sendFile(file);
});

router.get("/download/brain-sandbox", (_req, res) => {
  const file = path.join(BRIDGE_DIR, "tools", "sandbox.py");
  if (!fs.existsSync(file)) {
    res.status(404).json({ error: "File not found" });
    return;
  }
  res.setHeader("Content-Disposition", 'attachment; filename="sandbox.py"');
  res.setHeader("Content-Type", "text/plain; charset=utf-8");
  res.sendFile(file);
});

export default router;
