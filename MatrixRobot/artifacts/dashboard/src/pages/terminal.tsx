import { useState } from "react";
import {
  useGetActiveTrades,
  useGetDashboardStatus,
  getGetActiveTradesQueryKey,
  getGetDashboardStatusQueryKey,
} from "@workspace/api-client-react";
import { formatDistanceToNow } from "date-fns";

// ── Mock closed trades history ────────────────────────────────────────────────
const HISTORY = [
  { ticket: "T-0091", symbol: "EURUSD", type: "BUY",  lots: 0.10, openPrice: 1.07820, closePrice: 1.08210, sl: 1.075, tp: 1.085, profit: +39.00, openedAt: "2026-05-17T08:12:00Z", closedAt: "2026-05-17T14:35:00Z", reason: "TP hit" },
  { ticket: "T-0090", symbol: "GBPUSD", type: "SELL", lots: 0.05, openPrice: 1.28350, closePrice: 1.27910, sl: 1.287, tp: 1.275, profit: +22.00, openedAt: "2026-05-17T06:00:00Z", closedAt: "2026-05-17T11:20:00Z", reason: "TP hit" },
  { ticket: "T-0089", symbol: "USDJPY", type: "BUY",  lots: 0.10, openPrice: 149.20, closePrice: 148.80, sl: 148.5, tp: 150.5, profit: -40.00, openedAt: "2026-05-16T15:30:00Z", closedAt: "2026-05-16T18:00:00Z", reason: "SL hit" },
  { ticket: "T-0088", symbol: "XAUUSD", type: "BUY",  lots: 0.02, openPrice: 2298.0, closePrice: 2315.0, sl: 2280.0, tp: 2340.0, profit: +34.00, openedAt: "2026-05-16T09:00:00Z", closedAt: "2026-05-16T21:45:00Z", reason: "TP hit" },
  { ticket: "T-0087", symbol: "EURUSD", type: "SELL", lots: 0.10, openPrice: 1.08900, closePrice: 1.09100, sl: 1.093, tp: 1.083, profit: -20.00, openedAt: "2026-05-15T12:00:00Z", closedAt: "2026-05-15T16:30:00Z", reason: "SL hit" },
  { ticket: "T-0086", symbol: "GBPUSD", type: "BUY",  lots: 0.05, openPrice: 1.26500, closePrice: 1.27350, sl: 1.260, tp: 1.278, profit: +42.50, openedAt: "2026-05-15T07:30:00Z", closedAt: "2026-05-15T15:00:00Z", reason: "TP hit" },
  { ticket: "T-0085", symbol: "XAUUSD", type: "SELL", lots: 0.02, openPrice: 2340.0, closePrice: 2338.5, sl: 2355.0, tp: 2310.0, profit: +3.00, openedAt: "2026-05-14T10:00:00Z", closedAt: "2026-05-14T14:20:00Z", reason: "Manual" },
];

const totalHistoryProfit = HISTORY.reduce((s, t) => s + t.profit, 0);
const wins = HISTORY.filter((t) => t.profit > 0).length;
const winRate = Math.round((wins / HISTORY.length) * 100);

type Tab = "positions" | "history" | "summary";

function ProfitCell({ value }: { value: number }) {
  return (
    <td className={`px-2 py-2 font-mono text-right text-xs font-semibold ${value >= 0 ? "text-green-400" : "text-red-400"}`}>
      {value >= 0 ? "+" : ""}{value.toFixed(2)}
    </td>
  );
}

// ── Direction badge ───────────────────────────────────────────────────────────
function DirBadge({ dir }: { dir: string }) {
  const isBuy = dir === "BUY";
  return (
    <span className={`px-1.5 py-0.5 rounded text-[10px] font-bold border ${
      isBuy ? "text-green-400 border-green-500/30 bg-green-500/10" : "text-red-400 border-red-500/30 bg-red-500/10"
    }`}>
      {dir}
    </span>
  );
}

// ── Main Terminal page ────────────────────────────────────────────────────────
export default function Terminal() {
  const [tab, setTab] = useState<Tab>("positions");
  const { data: trades = [] } = useGetActiveTrades({ query: { refetchInterval: 10000, queryKey: getGetActiveTradesQueryKey() } });
  const { data: status } = useGetDashboardStatus({ query: { refetchInterval: 30000, queryKey: getGetDashboardStatusQueryKey() } });

  const account = status?.account ?? {
    balance: 10000,
    equity: 9901,
    currency: "USD",
    dailyDrawdownPct: 0.99,
    totalDrawdownPct: 3.57,
  };

  const openPnl = (trades as Array<{ pnl: number }>).reduce((s, t) => s + t.pnl, 0);
  const equity = (account as { equity: number }).equity;
  const balance = (account as { balance: number }).balance;
  const margin = (trades as Array<{ lots: number; openPrice: number }>).reduce(
    (s, t) => s + t.lots * t.openPrice * 0.01,
    0
  );
  const freeMargin = equity - margin;
  const marginLevel = margin > 0 ? (equity / margin) * 100 : 0;

  const TABS: { id: Tab; label: string; count?: number }[] = [
    { id: "positions", label: "Trade",    count: (trades as unknown[]).length },
    { id: "history",  label: "History",  count: HISTORY.length },
    { id: "summary",  label: "Summary" },
  ];

  return (
    <div className="flex flex-col h-full bg-[#0d0d0d] text-zinc-300 text-xs font-mono select-none">

      {/* ── Account bar (MT5 top strip) ──────────────────────────────────── */}
      <div className="grid grid-cols-3 sm:grid-cols-6 gap-px bg-[#1a1a1a] border-b border-[#27272a]">
        {[
          { label: "Balance",      value: `${balance.toLocaleString("en-US", { minimumFractionDigits: 2 })}` },
          { label: "Equity",       value: `${equity.toLocaleString("en-US", { minimumFractionDigits: 2 })}`,   colored: true, v: openPnl },
          { label: "Margin",       value: `${margin.toFixed(2)}` },
          { label: "Free Margin",  value: `${freeMargin.toFixed(2)}`,  colored: true, v: freeMargin },
          { label: "Margin Lvl",   value: marginLevel > 0 ? `${marginLevel.toFixed(1)}%` : "—" },
          { label: "Open P&L",     value: `${openPnl >= 0 ? "+" : ""}${openPnl.toFixed(2)}`, colored: true, v: openPnl },
        ].map((item) => (
          <div key={item.label} className="flex flex-col items-center py-2 px-2 bg-[#0d0d0d]">
            <span className="text-[9px] text-zinc-600 uppercase tracking-wider">{item.label}</span>
            <span className={`text-xs font-semibold mt-0.5 ${
              item.colored
                ? (item.v ?? 0) >= 0 ? "text-green-400" : "text-red-400"
                : "text-zinc-200"
            }`}>
              {item.value}
            </span>
          </div>
        ))}
      </div>

      {/* ── Tabs ─────────────────────────────────────────────────────────── */}
      <div className="flex border-b border-[#1a1a1a] bg-[#0a0a0a]">
        {TABS.map((t) => (
          <button
            key={t.id}
            onClick={() => setTab(t.id)}
            className={`flex items-center gap-1.5 px-4 py-2.5 text-[11px] font-semibold uppercase tracking-wider border-b-2 transition-colors ${
              tab === t.id
                ? "border-blue-500 text-blue-400"
                : "border-transparent text-zinc-500 hover:text-zinc-300"
            }`}
          >
            {t.label}
            {t.count !== undefined && (
              <span className={`text-[9px] px-1 rounded-sm ${
                tab === t.id ? "bg-blue-500/20 text-blue-400" : "bg-zinc-800 text-zinc-500"
              }`}>
                {t.count}
              </span>
            )}
          </button>
        ))}
      </div>

      {/* ── Open positions ────────────────────────────────────────────────── */}
      {tab === "positions" && (
        <div className="overflow-x-auto flex-1">
          {(trades as unknown[]).length === 0 ? (
            <div className="flex flex-col items-center justify-center h-32 text-zinc-700">
              <span className="text-sm">No open positions</span>
            </div>
          ) : (
            <table className="w-full min-w-[600px] border-collapse">
              <thead>
                <tr className="bg-[#111111] border-b border-[#1e1e1e]">
                  {["Ticket","Symbol","Type","Lots","Open","Current","S/L","T/P","P&L","Age","Source"].map((h) => (
                    <th key={h} className="px-2 py-2 text-left text-[9px] font-semibold text-zinc-600 uppercase tracking-wider whitespace-nowrap">
                      {h}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {(trades as Array<{
                  id: string; symbol: string; direction: string; lots: number;
                  openPrice: number; currentPrice: number; stopLoss: number;
                  takeProfit: number; pnl: number; openedAt: string; source: string;
                }>).map((t, i) => (
                  <tr
                    key={t.id}
                    className={`border-b border-[#141414] hover:bg-[#141414] transition-colors ${i % 2 === 0 ? "bg-[#0d0d0d]" : "bg-[#0f0f0f]"}`}
                  >
                    <td className="px-2 py-2 text-zinc-500 whitespace-nowrap">{t.id.toUpperCase()}</td>
                    <td className="px-2 py-2 font-semibold text-zinc-200 whitespace-nowrap">{t.symbol}</td>
                    <td className="px-2 py-2"><DirBadge dir={t.direction} /></td>
                    <td className="px-2 py-2 text-zinc-400">{t.lots.toFixed(2)}</td>
                    <td className="px-2 py-2 text-zinc-300">{t.openPrice.toFixed(t.symbol.includes("JPY") ? 3 : t.symbol.includes("XAU") ? 2 : 5)}</td>
                    <td className="px-2 py-2 text-blue-300">{t.currentPrice.toFixed(t.symbol.includes("JPY") ? 3 : t.symbol.includes("XAU") ? 2 : 5)}</td>
                    <td className="px-2 py-2 text-red-500">{t.stopLoss.toFixed(t.symbol.includes("JPY") ? 3 : t.symbol.includes("XAU") ? 2 : 5)}</td>
                    <td className="px-2 py-2 text-green-500">{t.takeProfit.toFixed(t.symbol.includes("JPY") ? 3 : t.symbol.includes("XAU") ? 2 : 5)}</td>
                    <ProfitCell value={t.pnl} />
                    <td className="px-2 py-2 text-zinc-600 whitespace-nowrap text-[10px]">
                      {formatDistanceToNow(new Date(t.openedAt), { addSuffix: false })}
                    </td>
                    <td className="px-2 py-2">
                      <span className={`text-[9px] px-1 py-0.5 rounded border ${
                        t.source === "AGENT"
                          ? "text-purple-400 border-purple-500/30 bg-purple-500/10"
                          : "text-zinc-500 border-zinc-700"
                      }`}>
                        {t.source}
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
              <tfoot>
                <tr className="bg-[#111111] border-t border-[#27272a]">
                  <td colSpan={8} className="px-2 py-2 text-zinc-600 text-[9px] uppercase tracking-wider">
                    {(trades as unknown[]).length} positions · Total P&L
                  </td>
                  <ProfitCell value={openPnl} />
                  <td colSpan={2} />
                </tr>
              </tfoot>
            </table>
          )}
        </div>
      )}

      {/* ── Closed trades history ─────────────────────────────────────────── */}
      {tab === "history" && (
        <div className="overflow-x-auto flex-1">
          <table className="w-full min-w-[720px] border-collapse">
            <thead>
              <tr className="bg-[#111111] border-b border-[#1e1e1e]">
                {["Ticket","Symbol","Type","Lots","Open","Close","Profit","Reason","Opened","Closed"].map((h) => (
                  <th key={h} className="px-2 py-2 text-left text-[9px] font-semibold text-zinc-600 uppercase tracking-wider whitespace-nowrap">
                    {h}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {HISTORY.map((t, i) => (
                <tr
                  key={t.ticket}
                  className={`border-b border-[#141414] hover:bg-[#141414] transition-colors ${i % 2 === 0 ? "bg-[#0d0d0d]" : "bg-[#0f0f0f]"}`}
                >
                  <td className="px-2 py-2 text-zinc-500">{t.ticket}</td>
                  <td className="px-2 py-2 font-semibold text-zinc-200">{t.symbol}</td>
                  <td className="px-2 py-2"><DirBadge dir={t.type} /></td>
                  <td className="px-2 py-2 text-zinc-400">{t.lots.toFixed(2)}</td>
                  <td className="px-2 py-2 text-zinc-400 font-mono">{t.openPrice.toFixed(t.symbol.includes("JPY") ? 3 : t.symbol.includes("XAU") ? 2 : 5)}</td>
                  <td className="px-2 py-2 text-zinc-300 font-mono">{t.closePrice.toFixed(t.symbol.includes("JPY") ? 3 : t.symbol.includes("XAU") ? 2 : 5)}</td>
                  <ProfitCell value={t.profit} />
                  <td className="px-2 py-2">
                    <span className={`text-[9px] px-1 py-0.5 rounded border ${
                      t.reason === "TP hit" ? "text-green-400 border-green-500/20 bg-green-500/10"
                      : t.reason === "SL hit" ? "text-red-400 border-red-500/20 bg-red-500/10"
                      : "text-zinc-500 border-zinc-700"
                    }`}>
                      {t.reason}
                    </span>
                  </td>
                  <td className="px-2 py-2 text-zinc-600 text-[10px] whitespace-nowrap">
                    {new Date(t.openedAt).toLocaleDateString("en-US", { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" })}
                  </td>
                  <td className="px-2 py-2 text-zinc-600 text-[10px] whitespace-nowrap">
                    {new Date(t.closedAt).toLocaleDateString("en-US", { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" })}
                  </td>
                </tr>
              ))}
            </tbody>
            <tfoot>
              <tr className="bg-[#111111] border-t border-[#27272a]">
                <td colSpan={6} className="px-2 py-2 text-zinc-600 text-[9px] uppercase tracking-wider">
                  {HISTORY.length} closed trades
                </td>
                <ProfitCell value={totalHistoryProfit} />
                <td colSpan={3} />
              </tr>
            </tfoot>
          </table>
        </div>
      )}

      {/* ── Summary ───────────────────────────────────────────────────────── */}
      {tab === "summary" && (
        <div className="p-4 grid grid-cols-1 sm:grid-cols-2 gap-4 max-w-2xl">

          {/* Account card */}
          <div className="bg-[#111111] border border-[#1e1e1e] rounded-lg p-4">
            <h3 className="text-[9px] uppercase tracking-widest text-zinc-600 mb-3">Account</h3>
            <div className="space-y-2">
              {[
                { label: "Balance",         value: `$${balance.toFixed(2)}`,         color: "text-zinc-200" },
                { label: "Equity",          value: `$${equity.toFixed(2)}`,          color: openPnl >= 0 ? "text-green-400" : "text-red-400" },
                { label: "Open P&L",        value: `${openPnl >= 0 ? "+" : ""}$${openPnl.toFixed(2)}`, color: openPnl >= 0 ? "text-green-400" : "text-red-400" },
                { label: "Daily Drawdown",  value: `${(account as { dailyDrawdownPct: number }).dailyDrawdownPct?.toFixed(2)}%`, color: "text-amber-400" },
                { label: "Total Drawdown",  value: `${(account as { totalDrawdownPct: number }).totalDrawdownPct?.toFixed(2)}%`, color: "text-amber-400" },
                { label: "Free Margin",     value: `$${freeMargin.toFixed(2)}`,      color: "text-zinc-300" },
              ].map((row) => (
                <div key={row.label} className="flex justify-between items-center border-b border-[#1a1a1a] pb-1.5">
                  <span className="text-[10px] text-zinc-600">{row.label}</span>
                  <span className={`text-xs font-semibold ${row.color}`}>{row.value}</span>
                </div>
              ))}
            </div>
          </div>

          {/* Performance card */}
          <div className="bg-[#111111] border border-[#1e1e1e] rounded-lg p-4">
            <h3 className="text-[9px] uppercase tracking-widest text-zinc-600 mb-3">Performance</h3>
            <div className="space-y-2">
              {[
                { label: "Total Trades",    value: String(HISTORY.length) },
                { label: "Winning Trades",  value: String(wins),          color: "text-green-400" },
                { label: "Losing Trades",   value: String(HISTORY.length - wins), color: "text-red-400" },
                { label: "Win Rate",        value: `${winRate}%`,         color: winRate >= 50 ? "text-green-400" : "text-red-400" },
                { label: "Closed P&L",      value: `${totalHistoryProfit >= 0 ? "+" : ""}$${totalHistoryProfit.toFixed(2)}`, color: totalHistoryProfit >= 0 ? "text-green-400" : "text-red-400" },
                { label: "Open Positions",  value: String((trades as unknown[]).length), color: "text-blue-400" },
              ].map((row) => (
                <div key={row.label} className="flex justify-between items-center border-b border-[#1a1a1a] pb-1.5">
                  <span className="text-[10px] text-zinc-600">{row.label}</span>
                  <span className={`text-xs font-semibold ${row.color ?? "text-zinc-200"}`}>{row.value}</span>
                </div>
              ))}
            </div>
          </div>

          {/* Risk limits */}
          <div className="sm:col-span-2 bg-[#111111] border border-[#1e1e1e] rounded-lg p-4">
            <h3 className="text-[9px] uppercase tracking-widest text-zinc-600 mb-3">Risk Limits</h3>
            <div className="grid grid-cols-2 sm:grid-cols-3 gap-3">
              {[
                { label: "Max Daily DD",    value: "2.5%", status: (account as { dailyDrawdownPct: number }).dailyDrawdownPct > 2 ? "warn" : "ok" },
                { label: "Max Total DD",    value: "8.0%", status: (account as { totalDrawdownPct: number }).totalDrawdownPct > 6 ? "warn" : "ok" },
                { label: "Risk Per Trade",  value: "1.5%", status: "ok" },
                { label: "Max Positions",   value: "5",    status: (trades as unknown[]).length >= 4 ? "warn" : "ok" },
                { label: "Current Mode",    value: "PAPER", status: "info" },
                { label: "Agent Source",    value: `${(trades as Array<{source:string}>).filter(t=>t.source==="AGENT").length}/${(trades as unknown[]).length}`, status: "info" },
              ].map((row) => (
                <div key={row.label} className="bg-[#0d0d0d] rounded p-2 border border-[#1a1a1a]">
                  <div className="text-[9px] text-zinc-600 mb-1">{row.label}</div>
                  <div className={`text-sm font-bold ${
                    row.status === "warn" ? "text-amber-400"
                    : row.status === "info" ? "text-blue-400"
                    : "text-green-400"
                  }`}>
                    {row.value}
                  </div>
                </div>
              ))}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
