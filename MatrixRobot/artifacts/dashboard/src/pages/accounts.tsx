import { useQuery } from "@tanstack/react-query";
import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { Progress } from "@/components/ui/progress";
import {
  Wallet,
  CheckCircle2,
  XCircle,
  TrendingUp,
  TrendingDown,
  Activity,
  ShieldCheck,
} from "lucide-react";

interface AccountRow {
  id: string;
  label: string;
  enabled: boolean;
  prop_firm: string | null;
  bridge_url_configured: boolean;
  risk_per_trade_pct: number;
  max_daily_drawdown_pct: number;
  max_total_drawdown_pct: number;
  open_positions: number;
  trades_today: number;
  trades_today_max: number;
  account: {
    available: boolean;
    equity: number | null;
    balance: number | null;
    starting_balance: number | null;
    daily_drawdown_pct: number | null;
    total_drawdown_pct: number | null;
    profit_pct: number | null;
    currency: string | null;
  };
}

interface AccountsResponse {
  accounts: AccountRow[];
  count: number;
}

function fmtUsd(v: number | null | undefined) {
  if (v === null || v === undefined) return "—";
  return `$${v.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
}

function fmtPct(v: number | null | undefined, digits = 2) {
  if (v === null || v === undefined) return "—";
  return `${v.toFixed(digits)}%`;
}

function AccountCard({ row }: { row: AccountRow }) {
  const a = row.account;
  const bridgeOk = row.bridge_url_configured && a.available;
  const profitPositive = (a.profit_pct ?? 0) >= 0;

  const dailyPct = (a.daily_drawdown_pct ?? 0) / row.max_daily_drawdown_pct * 100;
  const totalPct = (a.total_drawdown_pct ?? 0) / row.max_total_drawdown_pct * 100;
  const tradesPct = (row.trades_today / row.trades_today_max) * 100;

  return (
    <Card
      className="bg-card/40 border-border/50 overflow-hidden"
      data-testid={`card-account-${row.id}`}
    >
      <CardContent className="p-4 space-y-4">
        {/* Header */}
        <div className="flex items-start justify-between gap-3">
          <div className="flex items-start gap-3 min-w-0">
            <div className="shrink-0 h-10 w-10 rounded-lg bg-primary/10 text-primary border border-primary/20 flex items-center justify-center">
              <Wallet className="h-5 w-5" />
            </div>
            <div className="min-w-0">
              <div className="text-sm font-semibold truncate">{row.label}</div>
              <div className="text-[10px] font-mono text-muted-foreground uppercase tracking-wider">
                {row.id}
                {row.prop_firm ? ` · ${row.prop_firm}` : ""}
              </div>
            </div>
          </div>
          <div className="flex flex-col items-end gap-1">
            {bridgeOk ? (
              <Badge variant="outline" className="text-[10px] px-1.5 py-0 bg-emerald-500/10 text-emerald-400 border-emerald-500/30 gap-0.5">
                <CheckCircle2 className="h-2.5 w-2.5" /> Online
              </Badge>
            ) : (
              <Badge variant="outline" className="text-[10px] px-1.5 py-0 bg-secondary text-muted-foreground border-border gap-0.5">
                <XCircle className="h-2.5 w-2.5" /> Offline
              </Badge>
            )}
            {!row.enabled && (
              <Badge variant="outline" className="text-[10px] px-1.5 py-0 bg-amber-500/10 text-amber-400 border-amber-500/30">
                Disabled
              </Badge>
            )}
          </div>
        </div>

        {/* Equity row */}
        <div className="grid grid-cols-3 gap-2">
          <div className="space-y-0.5">
            <div className="text-[10px] uppercase tracking-wider text-muted-foreground">Equity</div>
            <div className="text-sm font-semibold font-mono">{fmtUsd(a.equity)}</div>
          </div>
          <div className="space-y-0.5">
            <div className="text-[10px] uppercase tracking-wider text-muted-foreground">Balance</div>
            <div className="text-sm font-mono">{fmtUsd(a.balance)}</div>
          </div>
          <div className="space-y-0.5">
            <div className="text-[10px] uppercase tracking-wider text-muted-foreground">P&amp;L</div>
            <div className={`text-sm font-semibold font-mono flex items-center gap-1 ${profitPositive ? "text-emerald-400" : "text-red-400"}`}>
              {profitPositive ? <TrendingUp className="h-3 w-3" /> : <TrendingDown className="h-3 w-3" />}
              {fmtPct(a.profit_pct)}
            </div>
          </div>
        </div>

        {/* Drawdown bars */}
        <div className="space-y-2.5">
          <DrawdownBar
            label="Daily Drawdown"
            currentPct={a.daily_drawdown_pct ?? 0}
            maxPct={row.max_daily_drawdown_pct}
            barPct={dailyPct}
          />
          <DrawdownBar
            label="Total Drawdown"
            currentPct={a.total_drawdown_pct ?? 0}
            maxPct={row.max_total_drawdown_pct}
            barPct={totalPct}
          />
          <div className="space-y-1">
            <div className="flex justify-between text-[10px] font-mono">
              <span className="text-muted-foreground uppercase tracking-wider flex items-center gap-1">
                <Activity className="h-2.5 w-2.5" /> Trades Today
              </span>
              <span className="text-foreground">
                {row.trades_today} / {row.trades_today_max}
              </span>
            </div>
            <Progress value={tradesPct} className="h-1.5" />
          </div>
        </div>

        {/* Footer */}
        <div className="grid grid-cols-2 gap-2 pt-2 border-t border-border/50 text-[10px] font-mono">
          <div className="flex items-center gap-1.5">
            <ShieldCheck className="h-3 w-3 text-muted-foreground" />
            <span className="text-muted-foreground">Risk/trade:</span>
            <span className="text-foreground font-semibold">{row.risk_per_trade_pct}%</span>
          </div>
          <div className="flex items-center gap-1.5 justify-end">
            <span className="text-muted-foreground">Open:</span>
            <span className="text-foreground font-semibold">{row.open_positions}</span>
          </div>
        </div>
      </CardContent>
    </Card>
  );
}

function DrawdownBar({
  label, currentPct, maxPct, barPct,
}: { label: string; currentPct: number; maxPct: number; barPct: number }) {
  const danger = barPct >= 80;
  const warn = barPct >= 50;
  const color = danger ? "bg-red-500" : warn ? "bg-amber-500" : "bg-emerald-500";
  return (
    <div className="space-y-1">
      <div className="flex justify-between text-[10px] font-mono">
        <span className="text-muted-foreground uppercase tracking-wider">{label}</span>
        <span className={danger ? "text-red-400" : warn ? "text-amber-400" : "text-foreground"}>
          {fmtPct(currentPct)} / {maxPct}%
        </span>
      </div>
      <div className="h-1.5 rounded-full bg-secondary overflow-hidden">
        <div
          className={`h-full rounded-full transition-all ${color}`}
          style={{ width: `${Math.min(100, Math.max(0, barPct))}%` }}
        />
      </div>
    </div>
  );
}

export default function Accounts() {
  const { data, isLoading, error } = useQuery<AccountsResponse>({
    queryKey: ["agents-accounts"],
    queryFn: async () => {
      const res = await fetch("/api/agents/accounts");
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      return res.json();
    },
    refetchInterval: 30_000,
  });

  if (isLoading) {
    return (
      <div className="p-4 space-y-4 max-w-3xl mx-auto">
        <Skeleton className="h-16 rounded-xl" />
        <Skeleton className="h-56 rounded-xl" />
      </div>
    );
  }

  if (error || !data) {
    return (
      <div className="p-4 max-w-3xl mx-auto">
        <Card className="bg-card/50 border-red-500/30">
          <CardContent className="p-4 text-sm text-red-400">
            Failed to load accounts: {String((error as Error)?.message ?? "unknown error")}
          </CardContent>
        </Card>
      </div>
    );
  }

  const isMulti = data.count > 1;
  const totalEquity = data.accounts.reduce(
    (s, a) => s + (a.account.equity ?? 0), 0,
  );

  return (
    <div className="p-4 flex flex-col gap-4 max-w-3xl mx-auto pb-16">
      {/* Summary header */}
      <Card className="bg-card/50 border-border/50">
        <CardContent className="p-4 flex items-center justify-between">
          <div className="flex items-center gap-2">
            <Wallet className="h-4 w-4 text-primary" />
            <span className="text-sm font-semibold">
              {data.count} Account{data.count === 1 ? "" : "s"} Connected
            </span>
          </div>
          <div className="text-right">
            <div className="text-[10px] uppercase tracking-wider text-muted-foreground">
              Total Equity
            </div>
            <div className="text-sm font-bold font-mono">{fmtUsd(totalEquity)}</div>
          </div>
        </CardContent>
      </Card>

      {/* Account cards */}
      <div className="space-y-3">
        {data.accounts.map((row) => (
          <AccountCard key={row.id} row={row} />
        ))}
      </div>

      {/* How-to add second account */}
      {!isMulti && (
        <Card className="bg-blue-500/5 border-blue-500/20">
          <CardContent className="p-4 space-y-2 text-xs">
            <div className="font-semibold text-blue-400 text-sm">
              Add a second account
            </div>
            <p className="text-muted-foreground leading-relaxed">
              To mirror signals onto another MT5 account (e.g. ForexIraq), set the{" "}
              <code className="font-mono text-foreground bg-secondary/60 px-1 rounded">
                ACCOUNTS_JSON
              </code>{" "}
              secret with an array of account configs. Each needs its own{" "}
              <code className="font-mono text-foreground bg-secondary/60 px-1 rounded">
                bridge_url
              </code>{" "}
              pointing to a separate MT5 Windows bridge instance (e.g. port 5556).
            </p>
            <pre className="font-mono text-[10px] bg-secondary/40 p-2 rounded overflow-x-auto text-foreground/80 leading-snug">{`[
  {
    "id": "forexiraq",
    "label": "ForexIraq Live",
    "bridge_url": "http://192.168.1.15:5556",
    "risk_per_trade_pct": 3.0,
    "max_daily_drawdown_pct": 10,
    "max_total_drawdown_pct": 25
  }
]`}</pre>
          </CardContent>
        </Card>
      )}
    </div>
  );
}
