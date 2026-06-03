import { Router, type IRouter } from "express";
import { buildSentimentReport } from "../services/sentiment";

const router: IRouter = Router();

// Cache the last report for 5 minutes to avoid hammering Polygon + OpenRouter APIs
let cachedReport: Awaited<ReturnType<typeof buildSentimentReport>> | null = null;
let cacheExpiry = 0;
const CACHE_TTL_MS = 5 * 60 * 1000;

router.get("/sentiment", async (req, res): Promise<void> => {
  const now = Date.now();

  if (cachedReport && now < cacheExpiry) {
    req.log.info("Serving cached sentiment report");
    res.json(cachedReport);
    return;
  }

  req.log.info("Building fresh sentiment report");
  const report = await buildSentimentReport();
  cachedReport = report;
  cacheExpiry = now + CACHE_TTL_MS;

  res.json(report);
});

export default router;
