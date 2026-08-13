import express, { type Express } from "express";
import cors from "cors";
import fs from "node:fs";
import path from "node:path";
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

function resolveDashboardDist(): string | null {
  const override = process.env["DASHBOARD_DIST"];
  const candidates = [
    override,
    path.resolve(__dirname, "../../dashboard/dist/public"),
    path.resolve(process.cwd(), "../dashboard/dist/public"),
    path.resolve(process.cwd(), "../../artifacts/dashboard/dist/public"),
  ].filter((p): p is string => Boolean(p));

  for (const dir of candidates) {
    if (fs.existsSync(path.join(dir, "index.html"))) {
      return dir;
    }
  }
  return null;
}

const dashboardDist = resolveDashboardDist();
if (dashboardDist) {
  logger.info({ dashboardDist }, "Serving dashboard SPA");
  app.use(express.static(dashboardDist));
  app.get(/.*/, (req, res, next) => {
    if (req.path.startsWith("/api")) {
      return next();
    }
    res.sendFile(path.join(dashboardDist, "index.html"));
  });
} else {
  logger.warn("Dashboard dist not found — API only mode");
}

export default app;
