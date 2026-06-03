import { useEffect, useRef, useMemo, useState, useCallback } from "react";
import {
  createChart,
  createSeriesMarkers,
  ColorType,
  CrosshairMode,
  LineStyle,
  CandlestickSeries,
  LineSeries,
  type IChartApi,
  type CandlestickData,
  type Time,
} from "lightweight-charts";
import { useGetActiveTrades, getGetActiveTradesQueryKey } from "@workspace/api-client-react";

// ── Types ─────────────────────────────────────────────────────────────────────
interface OHLCBar {
  time: number;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
}

interface OHLCResponse {
  symbol: string;
  source: "polygon" | "none";
  bars: OHLCBar[];
}

// ── Synthetic OHLC fallback ───────────────────────────────────────────────────
function generateCandles(
  basePrice: number,
  count: number,
  volatility: number,
  intervalMinutes: number
): CandlestickData[] {
  const now = Math.floor(Date.now() / 1000);
  const step = intervalMinutes * 60;
  let price = basePrice;
  const candles: CandlestickData[] = [];
  for (let i = count - 1; i >= 0; i--) {
    const t = (now - i * step) as Time;
    const open = price;
    const change = (Math.random() - 0.49) * volatility;
    const close = +(open + change).toFixed(5);
    const high = +(Math.max(open, close) + Math.random() * volatility * 0.5).toFixed(5);
    const low = +(Math.min(open, close) - Math.random() * volatility * 0.5).toFixed(5);
    candles.push({ time: t, open, high, low, close });
    price = close;
  }
  return candles;
}

// ── EMA ───────────────────────────────────────────────────────────────────────
function calcEMA(candles: CandlestickData[], period: number) {
  const k = 2 / (period + 1);
  let ema = candles[0].close;
  return candles.map((c, i) => {
    if (i === 0) return { time: c.time, value: c.close };
    ema = c.close * k + ema * (1 - k);
    return { time: c.time, value: +ema.toFixed(5) };
  });
}

// ── Symbol config ─────────────────────────────────────────────────────────────
const SYMBOLS = [
  { symbol: "EURUSD", base: 1.0862, vol: 0.0008, digits: 5 },
  { symbol: "GBPUSD", base: 1.2715, vol: 0.0012, digits: 5 },
  { symbol: "USDJPY", base: 149.85, vol: 0.08,   digits: 3 },
  { symbol: "XAUUSD", base: 2318.4, vol: 2.8,    digits: 2 },
];

const CHART_THEME = {
  background: "#0a0a0a",
  text:       "#a1a1aa",
  grid:       "#141414",
  border:     "#27272a",
  upColor:    "#22c55e",
  downColor:  "#ef4444",
  wickUp:     "#16a34a",
  wickDown:   "#dc2626",
  ema20:      "#3b82f6",
  ema50:      "#f59e0b",
};

// ── Custom hook: fetch OHLC from API ─────────────────────────────────────────
function useOHLC(symbol: string) {
  const [data, setData] = useState<{ candles: CandlestickData[]; source: string } | null>(null);
  const [loading, setLoading] = useState(true);

  const fetch_ = useCallback(async () => {
    setLoading(true);
    try {
      const res = await fetch(`/api/ohlc/${symbol}`);
      if (!res.ok) throw new Error("API error");
      const json: OHLCResponse = await res.json();
      if (json.source === "polygon" && json.bars.length > 0) {
        const candles = json.bars.map((b) => ({
          time: b.time as Time,
          open: b.open,
          high: b.high,
          low: b.low,
          close: b.close,
        }));
        setData({ candles, source: "polygon" });
      } else {
        throw new Error("no data");
      }
    } catch {
      // Fall back to synthetic
      const cfg = SYMBOLS.find((s) => s.symbol === symbol)!;
      const candles = generateCandles(cfg.base, 120, cfg.vol, 15);
      setData({ candles, source: "demo" });
    } finally {
      setLoading(false);
    }
  }, [symbol]);

  useEffect(() => {
    fetch_();
    const id = setInterval(fetch_, 60_000); // refresh every 60s
    return () => clearInterval(id);
  }, [fetch_]);

  return { data, loading, refresh: fetch_ };
}

// ── Single chart panel ────────────────────────────────────────────────────────
interface Trade {
  id: string;
  symbol: string;
  direction: string;
  openPrice: number;
  stopLoss: number;
  takeProfit: number;
  pnl: number;
  lots: number;
  currentPrice: number;
}

interface ChartPanelProps {
  symbol: string;
  digits: number;
  trades: Trade[];
}

function ChartPanel({ symbol, digits, trades }: ChartPanelProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const { data, loading, refresh } = useOHLC(symbol);

  const symbolTrades = trades.filter((t) => t.symbol === symbol);

  const ema20 = useMemo(
    () => (data?.candles ? calcEMA(data.candles, 20) : []),
    [data?.candles]
  );
  const ema50 = useMemo(
    () => (data?.candles ? calcEMA(data.candles, 50) : []),
    [data?.candles]
  );

  useEffect(() => {
    if (!containerRef.current || !data?.candles.length) return;

    // Destroy previous chart
    if (chartRef.current) {
      chartRef.current.remove();
      chartRef.current = null;
    }

    const chart = createChart(containerRef.current, {
      layout: {
        background: { type: ColorType.Solid, color: CHART_THEME.background },
        textColor: CHART_THEME.text,
        fontSize: 10,
      },
      grid: {
        vertLines: { color: CHART_THEME.grid },
        horzLines: { color: CHART_THEME.grid },
      },
      crosshair: { mode: CrosshairMode.Normal },
      rightPriceScale: {
        borderColor: CHART_THEME.border,
        scaleMargins: { top: 0.08, bottom: 0.08 },
      },
      timeScale: {
        borderColor: CHART_THEME.border,
        timeVisible: true,
        secondsVisible: false,
      },
      handleScroll: true,
      handleScale: true,
    });
    chartRef.current = chart;

    const candleSeries = chart.addSeries(CandlestickSeries, {
      upColor:         CHART_THEME.upColor,
      downColor:       CHART_THEME.downColor,
      borderUpColor:   CHART_THEME.upColor,
      borderDownColor: CHART_THEME.downColor,
      wickUpColor:     CHART_THEME.wickUp,
      wickDownColor:   CHART_THEME.wickDown,
    });
    candleSeries.setData(data.candles);

    const addLine = (color: string) =>
      chart.addSeries(LineSeries, { color, lineWidth: 1, priceLineVisible: false, lastValueVisible: false });

    const ema20Series = addLine(CHART_THEME.ema20);
    ema20Series.setData(ema20);

    const ema50Series = addLine(CHART_THEME.ema50);
    ema50Series.setData(ema50);

    // SL / TP / entry lines for open trades
    symbolTrades.forEach((trade) => {
      const isBuy = trade.direction === "BUY";
      candleSeries.createPriceLine({
        price: trade.stopLoss, color: "#ef4444", lineWidth: 1,
        lineStyle: LineStyle.Dashed, axisLabelVisible: true, title: "SL",
      });
      candleSeries.createPriceLine({
        price: trade.takeProfit, color: "#22c55e", lineWidth: 1,
        lineStyle: LineStyle.Dashed, axisLabelVisible: true, title: "TP",
      });
      candleSeries.createPriceLine({
        price: trade.openPrice,
        color: isBuy ? "#22c55e" : "#ef4444",
        lineWidth: 1, lineStyle: LineStyle.Solid,
        axisLabelVisible: true, title: isBuy ? "BUY" : "SELL",
      });
    });

    // Trade entry markers
    if (symbolTrades.length > 0 && data.candles.length > 15) {
      const markers = symbolTrades.map((trade, idx) => {
        const isBuy = trade.direction === "BUY";
        const ci = Math.max(0, data.candles.length - 15 - idx * 8);
        return {
          time: data.candles[ci].time,
          position: isBuy ? ("belowBar" as const) : ("aboveBar" as const),
          color: isBuy ? "#22c55e" : "#ef4444",
          shape: isBuy ? ("arrowUp" as const) : ("arrowDown" as const),
          text: `${isBuy ? "BUY" : "SELL"} ${trade.lots}`,
          size: 1,
        };
      });
      createSeriesMarkers(candleSeries, markers);
    }

    chart.timeScale().fitContent();

    const observer = new ResizeObserver(() => {
      if (containerRef.current)
        chart.applyOptions({ width: containerRef.current.clientWidth });
    });
    if (containerRef.current) observer.observe(containerRef.current);

    return () => {
      observer.disconnect();
      chart.remove();
      chartRef.current = null;
    };
  }, [data, ema20, ema50, symbol, symbolTrades]);

  const lastCandle = data?.candles[data.candles.length - 1];
  const prevCandle = data?.candles[data.candles.length - 2];
  const priceChange = lastCandle && prevCandle ? lastCandle.close - prevCandle.close : 0;
  const pricePct = prevCandle ? ((priceChange / prevCandle.close) * 100).toFixed(3) : "0.000";
  const isUp = priceChange >= 0;
  const trade = symbolTrades[0];
  const isLive = data?.source === "polygon";

  return (
    <div className="flex flex-col bg-[#0a0a0a] border border-[#27272a] rounded-lg overflow-hidden">
      {/* Header */}
      <div className="flex items-center justify-between px-3 py-2 border-b border-[#1a1a1a]">
        <div className="flex items-center gap-2">
          <span className="text-xs font-bold text-white font-mono">{symbol}</span>
          <span className="text-[10px] text-zinc-500">M15</span>
          {isLive ? (
            <span className="flex items-center gap-1">
              <span className="relative flex h-1.5 w-1.5">
                <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-green-400 opacity-75" />
                <span className="relative inline-flex rounded-full h-1.5 w-1.5 bg-green-500" />
              </span>
              <span className="text-[9px] text-green-500">Live</span>
            </span>
          ) : (
            <span className="text-[9px] text-zinc-600">Demo</span>
          )}
        </div>
        <div className="flex items-center gap-2">
          {lastCandle && (
            <>
              <span className={`text-xs font-mono font-semibold ${isUp ? "text-green-400" : "text-red-400"}`}>
                {lastCandle.close.toFixed(digits)}
              </span>
              <span className={`text-[10px] font-mono ${isUp ? "text-green-500" : "text-red-500"}`}>
                {isUp ? "+" : ""}{pricePct}%
              </span>
            </>
          )}
          {trade && (
            <span className={`text-[10px] px-1.5 py-0 rounded font-bold border ${
              trade.direction === "BUY"
                ? "text-green-400 border-green-500/30 bg-green-500/10"
                : "text-red-400 border-red-500/30 bg-red-500/10"
            }`}>
              {trade.direction}
            </span>
          )}
          <button onClick={refresh} className="text-zinc-600 hover:text-zinc-400 transition-colors">
            <svg className="h-3 w-3" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <path d="M3 12a9 9 0 0 1 9-9 9.75 9.75 0 0 1 6.74 2.74L21 8"/>
              <path d="M21 3v5h-5"/>
              <path d="M21 12a9 9 0 0 1-9 9 9.75 9.75 0 0 1-6.74-2.74L3 16"/>
              <path d="M8 16H3v5"/>
            </svg>
          </button>
        </div>
      </div>

      {/* EMA legend */}
      <div className="flex items-center gap-3 px-3 py-1 border-b border-[#1a1a1a]">
        <span className="text-[10px] flex items-center gap-1">
          <span className="inline-block w-3 h-0.5 bg-blue-500 rounded" />
          <span className="text-zinc-600">EMA 20</span>
        </span>
        <span className="text-[10px] flex items-center gap-1">
          <span className="inline-block w-3 h-0.5 bg-amber-500 rounded" />
          <span className="text-zinc-600">EMA 50</span>
        </span>
        {trade && (
          <>
            <span className="text-[10px] flex items-center gap-1 text-red-500">
              SL {trade.stopLoss.toFixed(digits)}
            </span>
            <span className="text-[10px] flex items-center gap-1 text-green-500">
              TP {trade.takeProfit.toFixed(digits)}
            </span>
          </>
        )}
      </div>

      {/* Chart area */}
      <div className="relative">
        {loading && (
          <div className="absolute inset-0 flex items-center justify-center bg-[#0a0a0a] z-10">
            <div className="flex items-center gap-2 text-zinc-600 text-xs">
              <svg className="animate-spin h-3 w-3" viewBox="0 0 24 24" fill="none">
                <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"/>
                <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"/>
              </svg>
              Loading...
            </div>
          </div>
        )}
        <div ref={containerRef} className="w-full h-44 sm:h-52" />
      </div>

      {/* Trade footer */}
      {trade ? (
        <div className="flex items-center justify-between px-3 py-1.5 border-t border-[#1a1a1a] bg-[#0f0f0f]">
          <div className="flex items-center gap-2 text-[10px] text-zinc-500 font-mono">
            <span>Open: {trade.openPrice.toFixed(digits)}</span>
            <span className="text-zinc-700">|</span>
            <span>Lots: {trade.lots}</span>
          </div>
          <span className={`text-[10px] font-mono font-semibold ${trade.pnl >= 0 ? "text-green-400" : "text-red-400"}`}>
            {trade.pnl >= 0 ? "+" : ""}{trade.pnl.toFixed(2)}
          </span>
        </div>
      ) : (
        <div className="px-3 py-1.5 border-t border-[#1a1a1a] bg-[#0f0f0f]">
          <span className="text-[10px] text-zinc-700 font-mono">No open position</span>
        </div>
      )}
    </div>
  );
}

// ── Main Charts page ──────────────────────────────────────────────────────────
export default function Charts() {
  const { data: trades = [] } = useGetActiveTrades({ query: { refetchInterval: 10000, queryKey: getGetActiveTradesQueryKey() } });
  const hasPolygon = !!import.meta.env.VITE_HAS_POLYGON; // optional env flag

  return (
    <div className="p-3 sm:p-4 max-w-3xl mx-auto">
      <div className="mb-3 flex items-center justify-between">
        <div>
          <h2 className="text-sm font-semibold text-zinc-300 tracking-tight">Live Charts</h2>
          <p className="text-[10px] text-zinc-600 mt-0.5">
            M15 · EMA 20/50 · {hasPolygon ? "Polygon.io live data" : "Robot entry markers"}
          </p>
        </div>
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
        {SYMBOLS.map((cfg) => (
          <ChartPanel
            key={cfg.symbol}
            symbol={cfg.symbol}
            digits={cfg.digits}
            trades={trades as Trade[]}
          />
        ))}
      </div>
    </div>
  );
}
