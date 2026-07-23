import fs from "node:fs";
import path from "node:path";
import express, { type Express } from "express";
import cors from "cors";
import pinoHttp from "pino-http";
import router from "./routes";
import { logger } from "./lib/logger";

const app: Express = express();

app.use(
  pinoHttp({
    logger,
    serializers: {
      req(req) {
        return {
          id: req.id,
          method: req.method,
          url: req.url?.split("?")[0],
        };
      },
      res(res) {
        return {
          statusCode: res.statusCode,
        };
      },
    },
  }),
);
app.use(cors());
app.use(express.json());
app.use(express.urlencoded({ extended: true }));

app.use("/api", router);

/** Resolve built dashboard (SPA) for single-port VPS hosting. */
function resolveDashboardDist(): string | null {
  const fromEnv = process.env["DASHBOARD_DIST"]?.trim();
  if (fromEnv && fs.existsSync(path.join(fromEnv, "index.html"))) {
    return fromEnv;
  }

  const candidates = [
    // Started with cwd = repo root
    path.resolve(process.cwd(), "artifacts/dashboard/dist/public"),
    // Started with cwd = artifacts/api-server (Windows launcher)
    path.resolve(process.cwd(), "../dashboard/dist/public"),
    path.resolve(process.cwd(), "dist/public"),
  ];

  for (const candidate of candidates) {
    if (fs.existsSync(path.join(candidate, "index.html"))) {
      return candidate;
    }
  }
  return null;
}

const dashboardDist = resolveDashboardDist();
if (dashboardDist) {
  logger.info({ dashboardDist }, "Serving dashboard SPA from API server");
  app.use(express.static(dashboardDist, { index: false }));
  app.use((req, res, next) => {
    if (req.method !== "GET" && req.method !== "HEAD") {
      next();
      return;
    }
    if (req.path.startsWith("/api")) {
      next();
      return;
    }
    res.sendFile(path.join(dashboardDist, "index.html"), (err) => {
      if (err) next(err);
    });
  });
} else {
  logger.info("No dashboard build found — API-only mode");
}

export default app;
