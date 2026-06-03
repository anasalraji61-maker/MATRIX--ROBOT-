import { Router, type IRouter } from "express";
import { logger } from "../lib/logger";

const router: IRouter = Router();

// ── In-memory trade store (replace with MT5 bridge when connected) ─────────
// Trades survive the request but reset on server restart — that's fine for demo/PAPER mode.

interface Trade {
  id: string;
  symbol: string;
  direction: "BUY" | "SELL";
  lots: number;
  openPrice: number;
  currentPrice: number;
  pnl: number;
  pnlPct: number;
  openedAt: string;
  stopLoss: number | null;
  takeProfit: number | null;
  source: "AGENT" | "MANUAL";
}

// Realistic demo positions to show the UI working in PAPER_MODE
const trades = new Map<string, Trade>([
  [
    "t-001",
    {
      id: "t-001",
      symbol: "EURUSD",
      direction: "BUY",
      lots: 0.1,
      openPrice: 1.08425,
      currentPrice: 1.08671,
      pnl: 24.6,
      pnlPct: 0.23,
      openedAt: new Date(Date.now() - 1000 * 60 * 47).toISOString(),
      stopLoss: 1.0810,
      takeProfit: 1.0920,
      source: "AGENT",
    },
  ],
  [
    "t-002",
    {
      id: "t-002",
      symbol: "GBPUSD",
      direction: "SELL",
      lots: 0.05,
      openPrice: 1.27340,
      currentPrice: 1.27115,
      pnl: 11.25,
      pnlPct: 0.18,
      openedAt: new Date(Date.now() - 1000 * 60 * 123).toISOString(),
      stopLoss: 1.2780,
      takeProfit: 1.2650,
      source: "AGENT",
    },
  ],
  [
    "t-003",
    {
      id: "t-003",
      symbol: "XAUUSD",
      direction: "BUY",
      lots: 0.02,
      openPrice: 2318.40,
      currentPrice: 2314.80,
      pnl: -7.2,
      pnlPct: -0.16,
      openedAt: new Date(Date.now() - 1000 * 60 * 210).toISOString(),
      stopLoss: 2295.00,
      takeProfit: 2355.00,
      source: "MANUAL",
    },
  ],
]);

function tickPrices() {
  // Simulate gentle price movement every call so the dashboard shows live feel
  for (const trade of trades.values()) {
    const pip = trade.symbol === "XAUUSD" ? 0.1 : 0.0001;
    const move = (Math.random() - 0.48) * pip * 5;
    trade.currentPrice = +(trade.currentPrice + move).toFixed(
      trade.symbol === "XAUUSD" ? 2 : 5
    );
    const diff =
      trade.direction === "BUY"
        ? trade.currentPrice - trade.openPrice
        : trade.openPrice - trade.currentPrice;
    const pipValue = trade.symbol === "XAUUSD" ? 100 : 10000;
    trade.pnl = +(diff * pipValue * trade.lots).toFixed(2);
    trade.pnlPct = +((trade.pnl / (trade.openPrice * trade.lots * 1000)) * 100).toFixed(3);
  }
}

// ── Routes ────────────────────────────────────────────────────────────────

router.get("/trades", (req, res): void => {
  req.log.info("Fetching active trades");
  tickPrices();
  res.json(Array.from(trades.values()));
});

router.post("/trades/:tradeId/close", (req, res): void => {
  const { tradeId } = req.params;
  req.log.info({ tradeId }, "Manual close requested");

  const trade = trades.get(tradeId);
  if (!trade) {
    res.status(404).json({ success: false, message: "Trade not found", tradeId });
    return;
  }

  trades.delete(tradeId);
  logger.info(
    { tradeId, symbol: trade.symbol, pnl: trade.pnl },
    "Trade manually closed"
  );

  res.json({
    success: true,
    message: `${trade.symbol} ${trade.direction} position closed at ${trade.currentPrice}. P&L: ${trade.pnl >= 0 ? "+" : ""}${trade.pnl.toFixed(2)} USD`,
    tradeId,
  });
});

router.post("/trades/:tradeId/increase", (req, res): void => {
  const { tradeId } = req.params;
  const { lots } = req.body as { lots?: number };
  req.log.info({ tradeId, lots }, "Manual increase requested");

  const trade = trades.get(tradeId);
  if (!trade) {
    res.status(404).json({ success: false, message: "Trade not found", tradeId });
    return;
  }

  if (!lots || lots <= 0 || lots > 10) {
    res.status(400).json({ success: false, message: "lots must be between 0.01 and 10", tradeId });
    return;
  }

  const prevLots = trade.lots;
  trade.lots = +(trade.lots + lots).toFixed(2);
  // Recalculate blended open price
  trade.openPrice = +((trade.openPrice * prevLots + trade.currentPrice * lots) / trade.lots).toFixed(5);

  logger.info(
    { tradeId, prevLots, newLots: trade.lots },
    "Trade position increased"
  );

  res.json({
    success: true,
    message: `${trade.symbol} position increased by ${lots} lots. New size: ${trade.lots} lots at blended price ${trade.openPrice}`,
    tradeId,
  });
});

export default router;
