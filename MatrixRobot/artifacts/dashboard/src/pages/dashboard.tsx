import { useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import {
  useGetDashboardStatus,
  useGetLatestNews,
  useGetAgentDecisions,
  useRefreshDashboard,
  useGetSentiment,
  useGetActiveTrades,
  useCloseTrade,
  useIncreaseTrade,
  useGetAgentServiceStatus,
  useRunAgentCycle,
  useGetAgentCycleStatus,
  useGetTradingMode,
  useSetTradingMode,
  useGetSchedulerStatus,
  useStartScheduler,
  useStopScheduler,
  useGetLivePositions,
  useCloseAgentPosition,
  useGetUsageStats,
  useGetStrategyScores,
  useGetPnlSummary,
  getGetUsageStatsQueryKey,
  getGetStrategyScoresQueryKey,
  getGetPnlSummaryQueryKey,
  getGetDashboardStatusQueryKey,
  getGetLatestNewsQueryKey,
  getGetAgentDecisionsQueryKey,
  getGetSentimentQueryKey,
  getGetActiveTradesQueryKey,
  getGetAgentCycleStatusQueryKey,
  getGetAgentServiceStatusQueryKey,
  getGetTradingModeQueryKey,
  getGetSchedulerStatusQueryKey,
  getGetLivePositionsQueryKey,
} from "@workspace/api-client-react";
import SystemStack from "./stack";
import Charts from "./charts";
import Terminal from "./terminal";
import Accounts from "./accounts";
import Tools from "./tools";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { formatDistanceToNow, format } from "date-fns";
import {
  RefreshCw,
  Activity,
  AlertTriangle,
  CheckCircle2,
  XCircle,
  Clock,
  Server,
  BarChart3,
  Bot,
  Newspaper,
  Brain,
  TrendingUp,
  TrendingDown,
  Minus,
  Radio,
  ArrowUpCircle,
  X,
  Plus,
  ChevronsUpDown,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Progress } from "@/components/ui/progress";
import { Skeleton } from "@/components/ui/skeleton";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Input } from "@/components/ui/input";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogFooter,
} from "@/components/ui/dialog";
import { Switch } from "@/components/ui/switch";
import { Zap, Timer, ShieldAlert, ShieldCheck } from "lucide-react";

type SentimentLabel = "BULLISH" | "BEARISH" | "NEUTRAL";

function SentimentBadge({ label }: { label: SentimentLabel }) {
  const cfg = {
    BULLISH: {
      cls: "bg-emerald-500/10 text-emerald-400 border-emerald-500/30",
      Icon: TrendingUp,
    },
    BEARISH: {
      cls: "bg-red-500/10 text-red-400 border-red-500/30",
      Icon: TrendingDown,
    },
    NEUTRAL: {
      cls: "bg-blue-500/10 text-blue-400 border-blue-500/30",
      Icon: Minus,
    },
  }[label];

  return (
    <Badge
      variant="outline"
      className={`flex items-center gap-1 text-[10px] px-1.5 py-0 ${cfg.cls}`}
    >
      <cfg.Icon className="h-2.5 w-2.5" />
      {label}
    </Badge>
  );
}

function ScoreBar({ score }: { score: number }) {
  const pct = Math.round(((score + 1) / 2) * 100);
  const color =
    score > 0.15
      ? "bg-emerald-500"
      : score < -0.15
      ? "bg-red-500"
      : "bg-blue-500";
  return (
    <div className="flex items-center gap-2 text-xs text-muted-foreground">
      <span className="w-12 text-right font-mono">BEAR</span>
      <div className="flex-1 relative h-2 rounded-full bg-secondary overflow-hidden">
        <div
          className={`absolute top-0 h-full rounded-full transition-all ${color}`}
          style={{ width: `${pct}%` }}
        />
        <div className="absolute top-0 left-1/2 h-full w-px bg-border/60" />
      </div>
      <span className="w-12 font-mono">BULL</span>
    </div>
  );
}

// ── Trade Management Section ──────────────────────────────────────────

interface CloseConfirmProps {
  tradeId: string | null;
  symbol: string;
  pnl: number;
  onConfirm: () => void;
  onCancel: () => void;
  isPending: boolean;
}

function CloseConfirmDialog({
  tradeId,
  symbol,
  pnl,
  onConfirm,
  onCancel,
  isPending,
}: CloseConfirmProps) {
  return (
    <AlertDialog open={!!tradeId}>
      <AlertDialogContent className="bg-card border-border max-w-sm mx-4">
        <AlertDialogHeader>
          <AlertDialogTitle>Close {symbol} Position?</AlertDialogTitle>
          <AlertDialogDescription className="space-y-1">
            <span className="block">This will close the position immediately.</span>
            <span
              className={`block font-semibold ${pnl >= 0 ? "text-emerald-400" : "text-red-400"}`}
            >
              Unrealised P&L: {pnl >= 0 ? "+" : ""}
              {pnl.toFixed(2)} USD
            </span>
          </AlertDialogDescription>
        </AlertDialogHeader>
        <AlertDialogFooter>
          <AlertDialogCancel onClick={onCancel} disabled={isPending}>
            Cancel
          </AlertDialogCancel>
          <AlertDialogAction
            onClick={onConfirm}
            disabled={isPending}
            className="bg-red-600 hover:bg-red-700 text-white"
          >
            {isPending ? "Closing..." : "Close Trade"}
          </AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  );
}

interface IncreaseDialogProps {
  tradeId: string | null;
  symbol: string;
  direction: string;
  currentLots: number;
  onConfirm: (lots: number) => void;
  onCancel: () => void;
  isPending: boolean;
}

function IncreasePositionDialog({
  tradeId,
  symbol,
  direction,
  currentLots,
  onConfirm,
  onCancel,
  isPending,
}: IncreaseDialogProps) {
  const [lots, setLots] = useState("0.01");
  const parsed = parseFloat(lots);
  const valid = !isNaN(parsed) && parsed >= 0.01 && parsed <= 10;

  return (
    <Dialog open={!!tradeId} onOpenChange={(open) => !open && onCancel()}>
      <DialogContent className="bg-card border-border max-w-sm mx-4">
        <DialogHeader>
          <DialogTitle>
            Add to {symbol} {direction}
          </DialogTitle>
        </DialogHeader>
        <div className="space-y-4 py-2">
          <div className="text-sm text-muted-foreground">
            Current size:{" "}
            <span className="text-foreground font-mono font-medium">
              {currentLots} lots
            </span>
          </div>
          <div className="space-y-2">
            <label className="text-sm font-medium">Additional lots</label>
            <Input
              type="number"
              value={lots}
              onChange={(e) => setLots(e.target.value)}
              min="0.01"
              max="10"
              step="0.01"
              placeholder="0.01"
              className="font-mono"
            />
            {!valid && lots !== "" && (
              <p className="text-xs text-red-400">Enter between 0.01 and 10 lots</p>
            )}
            {valid && (
              <p className="text-xs text-muted-foreground">
                New total: {(currentLots + parsed).toFixed(2)} lots
              </p>
            )}
          </div>
        </div>
        <DialogFooter className="gap-2">
          <Button variant="outline" onClick={onCancel} disabled={isPending}>
            Cancel
          </Button>
          <Button
            onClick={() => onConfirm(parsed)}
            disabled={!valid || isPending}
            className="bg-blue-600 hover:bg-blue-700"
          >
            {isPending ? "Adding..." : "Add to Position"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

// ── Main Dashboard ────────────────────────────────────────────────────────

export default function Dashboard() {
  const queryClient = useQueryClient();

  // Dialogs state
  const [closeTarget, setCloseTarget] = useState<{
    id: string;
    symbol: string;
    pnl: number;
  } | null>(null);
  const [increaseTarget, setIncreaseTarget] = useState<{
    id: string;
    symbol: string;
    direction: string;
    lots: number;
  } | null>(null);

  const [lastActionMsg, setLastActionMsg] = useState<string | null>(null);

  // Trading controls state
  const [modeConfirm, setModeConfirm] = useState<"ACTIVE" | "FROZEN" | null>(null);
  const [schedulerInterval, setSchedulerInterval] = useState("30");
  const [agentCloseTarget, setAgentCloseTarget] = useState<{
    id: string;
    symbol: string;
    profit: number;
  } | null>(null);

  // Queries
  const {
    data: status,
    isLoading: statusLoading,
    isError: statusError,
  } = useGetDashboardStatus({
    query: { refetchInterval: 30000, queryKey: getGetDashboardStatusQueryKey() },
  });

  const { data: news, isLoading: newsLoading } = useGetLatestNews({
    query: { refetchInterval: 30000, queryKey: getGetLatestNewsQueryKey() },
  });

  const { data: decisions, isLoading: decisionsLoading } = useGetAgentDecisions({
    query: { refetchInterval: 30000, queryKey: getGetAgentDecisionsQueryKey() },
  });

  const { data: sentiment, isLoading: sentimentLoading } = useGetSentiment({
    query: { refetchInterval: 5 * 60 * 1000, queryKey: getGetSentimentQueryKey() },
  });

  const { data: tradesRaw, isLoading: tradesLoading } = useGetActiveTrades({
    query: { refetchInterval: 10000, queryKey: getGetActiveTradesQueryKey() },
  });
  const trades = Array.isArray(tradesRaw) ? tradesRaw : [];

  const { data: agentService } = useGetAgentServiceStatus({
    query: { refetchInterval: 30000, queryKey: getGetAgentServiceStatusQueryKey() },
  });

  const { data: cycleStatus, refetch: refetchCycle } = useGetAgentCycleStatus({
    query: { refetchInterval: 15000, queryKey: getGetAgentCycleStatusQueryKey(), retry: false },
  });

  const { data: tradingMode, refetch: refetchMode } = useGetTradingMode({
    query: { refetchInterval: 15000, queryKey: getGetTradingModeQueryKey(), retry: false },
  });

  const { data: schedulerStatus, refetch: refetchScheduler } = useGetSchedulerStatus({
    query: { refetchInterval: 10000, queryKey: getGetSchedulerStatusQueryKey(), retry: false },
  });

  const { data: usageStats } = useGetUsageStats({
    query: { refetchInterval: 120000, queryKey: getGetUsageStatsQueryKey() },
  });

  const { data: strategyScores } = useGetStrategyScores(
    {},
    { query: { refetchInterval: 60000, queryKey: getGetStrategyScoresQueryKey({}) } },
  );

  const { data: pnlSummary } = useGetPnlSummary({
    query: { refetchInterval: 30000, queryKey: getGetPnlSummaryQueryKey() },
  });

  const { data: livePositions, refetch: refetchPositions } = useGetLivePositions({
    query: { refetchInterval: 15000, queryKey: getGetLivePositionsQueryKey(), retry: false },
  });

  // Mutations
  const refreshMutation = useRefreshDashboard();
  const closeMutation = useCloseTrade();
  const increaseMutation = useIncreaseTrade();
  const runCycleMutation = useRunAgentCycle();
  const setModeMutation = useSetTradingMode();
  const startSchedulerMutation = useStartScheduler();
  const stopSchedulerMutation = useStopScheduler();
  const closeAgentPositionMutation = useCloseAgentPosition();

  const isAnyLoading =
    statusLoading ||
    newsLoading ||
    decisionsLoading ||
    sentimentLoading ||
    tradesLoading ||
    refreshMutation.isPending;

  const handleRefresh = async () => {
    await refreshMutation.mutateAsync(undefined);
    queryClient.invalidateQueries({ queryKey: getGetDashboardStatusQueryKey() });
    queryClient.invalidateQueries({ queryKey: getGetLatestNewsQueryKey() });
    queryClient.invalidateQueries({ queryKey: getGetAgentDecisionsQueryKey() });
    queryClient.invalidateQueries({ queryKey: getGetSentimentQueryKey() });
    queryClient.invalidateQueries({ queryKey: getGetActiveTradesQueryKey() });
  };

  const handleCloseConfirm = async () => {
    if (!closeTarget) return;
    const result = await closeMutation.mutateAsync({ tradeId: closeTarget.id });
    setCloseTarget(null);
    setLastActionMsg(result.message);
    queryClient.invalidateQueries({ queryKey: getGetActiveTradesQueryKey() });
    setTimeout(() => setLastActionMsg(null), 6000);
  };

  const handleIncreaseConfirm = async (lots: number) => {
    if (!increaseTarget) return;
    const result = await increaseMutation.mutateAsync({
      tradeId: increaseTarget.id,
      data: { lots },
    });
    setIncreaseTarget(null);
    setLastActionMsg(result.message);
    queryClient.invalidateQueries({ queryKey: getGetActiveTradesQueryKey() });
    setTimeout(() => setLastActionMsg(null), 6000);
  };

  if (statusError) {
    return (
      <div className="min-h-[100dvh] bg-background p-4 flex flex-col items-center justify-center text-center space-y-4">
        <AlertTriangle className="h-12 w-12 text-destructive" />
        <h2 className="text-xl font-bold text-foreground">System Offline</h2>
        <p className="text-muted-foreground max-w-sm">
          Cannot connect to the trading monitor server. Please ensure the API is running.
        </p>
        <Button onClick={handleRefresh} variant="outline" className="mt-4">
          <RefreshCw className="mr-2 h-4 w-4" />
          Retry Connection
        </Button>
      </div>
    );
  }

  const formatCurrency = (value: number, currency: string) =>
    new Intl.NumberFormat("en-US", {
      style: "currency",
      currency,
      minimumFractionDigits: 2,
    }).format(value);

  return (
    <div className="min-h-[100dvh] bg-background text-foreground pb-16">
      {/* Header */}
      <header
        className="sticky top-0 z-10 bg-background/80 backdrop-blur-md border-b border-border p-4 flex items-center justify-between"
        data-testid="header"
      >
        <div>
          <h1 className="text-lg font-bold tracking-tight flex items-center gap-2">
            <Activity className="h-5 w-5 text-primary" />
            Matrix Robot
          </h1>
          {status?.lastUpdated ? (
            <p className="text-xs text-muted-foreground flex items-center gap-1 mt-0.5">
              <Clock className="h-3 w-3" />
              {format(new Date(status.lastUpdated), "HH:mm:ss")}
            </p>
          ) : (
            <Skeleton className="h-4 w-24 mt-1" />
          )}
        </div>
        <Button
          variant="outline"
          size="icon"
          onClick={handleRefresh}
          disabled={isAnyLoading}
          data-testid="button-refresh"
          className="shrink-0 rounded-full bg-secondary/50 border-secondary"
        >
          <RefreshCw className={`h-4 w-4 ${isAnyLoading ? "animate-spin" : ""}`} />
        </Button>
      </header>

      {/* Action feedback banner */}
      {lastActionMsg && (
        <div className="bg-emerald-900/40 border-b border-emerald-800 text-emerald-300 text-xs px-4 py-2.5 flex items-center justify-between gap-2">
          <span className="line-clamp-2">{lastActionMsg}</span>
          <button
            onClick={() => setLastActionMsg(null)}
            className="shrink-0 text-emerald-400 hover:text-emerald-200"
          >
            <X className="h-3.5 w-3.5" />
          </button>
        </div>
      )}

      <Tabs defaultValue="dashboard" className="flex-1">
        <div className="sticky top-[73px] z-10 bg-background/95 backdrop-blur-md border-b border-border">
          <TabsList className="grid grid-cols-6 w-full max-w-3xl mx-auto rounded-none border-0 bg-transparent h-auto py-0 px-2">
            <TabsTrigger
              value="dashboard"
              className="rounded-none border-b-2 border-transparent data-[state=active]:border-primary data-[state=active]:bg-transparent data-[state=active]:shadow-none py-3 text-[10px] font-semibold uppercase tracking-wider"
            >
              Dashboard
            </TabsTrigger>
            <TabsTrigger
              value="charts"
              className="rounded-none border-b-2 border-transparent data-[state=active]:border-primary data-[state=active]:bg-transparent data-[state=active]:shadow-none py-3 text-[10px] font-semibold uppercase tracking-wider"
            >
              Charts
            </TabsTrigger>
            <TabsTrigger
              value="terminal"
              className="rounded-none border-b-2 border-transparent data-[state=active]:border-primary data-[state=active]:bg-transparent data-[state=active]:shadow-none py-3 text-[10px] font-semibold uppercase tracking-wider"
            >
              Terminal
            </TabsTrigger>
            <TabsTrigger
              value="stack"
              className="rounded-none border-b-2 border-transparent data-[state=active]:border-primary data-[state=active]:bg-transparent data-[state=active]:shadow-none py-3 text-[10px] font-semibold uppercase tracking-wider"
            >
              Stack
            </TabsTrigger>
            <TabsTrigger
              value="accounts"
              className="rounded-none border-b-2 border-transparent data-[state=active]:border-primary data-[state=active]:bg-transparent data-[state=active]:shadow-none py-3 text-[10px] font-semibold uppercase tracking-wider"
            >
              Accounts
            </TabsTrigger>
            <TabsTrigger
              value="tools"
              className="rounded-none border-b-2 border-transparent data-[state=active]:border-primary data-[state=active]:bg-transparent data-[state=active]:shadow-none py-3 text-[10px] font-semibold uppercase tracking-wider"
            >
              Tools
            </TabsTrigger>
          </TabsList>
        </div>

        <TabsContent value="dashboard" className="mt-0 focus-visible:outline-none focus-visible:ring-0">
        <main className="p-4 flex flex-col gap-6 max-w-3xl mx-auto">

        {/* Trading State Banner */}
        <section data-testid="status-trading-state">
          {statusLoading ? (
            <Skeleton className="h-24 w-full rounded-xl" />
          ) : status ? (
            <div
              className={`p-6 rounded-xl border flex flex-col items-center justify-center text-center space-y-3 transition-colors ${
                status.tradingState === "ACTIVE"
                  ? "bg-emerald-950/20 border-emerald-900/50"
                  : status.tradingState === "FROZEN"
                  ? "bg-red-950/20 border-red-900/50"
                  : "bg-blue-950/20 border-blue-900/50"
              }`}
            >
              <Badge
                variant="outline"
                className={`text-sm px-3 py-1 font-mono tracking-widest ${
                  status.tradingState === "ACTIVE"
                    ? "bg-emerald-500/10 text-emerald-400 border-emerald-500/20"
                    : status.tradingState === "FROZEN"
                    ? "bg-red-500/10 text-red-400 border-red-500/20 animate-pulse"
                    : "bg-blue-500/10 text-blue-400 border-blue-500/20"
                }`}
              >
                {(status.tradingState ?? "PAPER_MODE").replace(/_/g, " ")}
              </Badge>
              <div className="flex items-center gap-2 text-sm text-muted-foreground font-medium">
                <span className="relative flex h-2.5 w-2.5">
                  {status.systemOnline && (
                    <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75" />
                  )}
                  <span
                    className={`relative inline-flex rounded-full h-2.5 w-2.5 ${
                      status.systemOnline ? "bg-emerald-500" : "bg-red-500"
                    }`}
                  />
                </span>
                {status.systemOnline ? "System Online" : "System Offline"}
              </div>
            </div>
          ) : null}
        </section>

        {/* Alert Banners */}
        {status?.account && (
          <section className="flex flex-col gap-3" data-testid="section-alerts">
            {status.account.dailyDrawdownPct >= status.account.dailyLimitPct && (
              <Alert variant="destructive" className="bg-red-950/50 border-red-900 text-red-200">
                <AlertTriangle className="h-5 w-5 text-red-400" />
                <AlertTitle className="text-red-400 font-semibold">
                  Critical: Daily Limit Breached
                </AlertTitle>
                <AlertDescription>
                  Daily drawdown ({status.account.dailyDrawdownPct}%) has exceeded the{" "}
                  {status.account.dailyLimitPct}% limit.
                </AlertDescription>
              </Alert>
            )}
            {status.account.dailyDrawdownPct >= 2.0 &&
              status.account.dailyDrawdownPct < status.account.dailyLimitPct && (
                <Alert className="bg-amber-950/30 border-amber-900/50 text-amber-200">
                  <AlertTriangle className="h-5 w-5 text-amber-400" />
                  <AlertTitle className="text-amber-400 font-semibold">
                    Warning: Daily Drawdown
                  </AlertTitle>
                  <AlertDescription>
                    Daily drawdown ({status.account.dailyDrawdownPct}%) is approaching the{" "}
                    {status.account.dailyLimitPct}% limit.
                  </AlertDescription>
                </Alert>
              )}
            {status.account.totalDrawdownPct >= status.account.totalLimitPct && (
              <Alert variant="destructive" className="bg-red-950/50 border-red-900 text-red-200">
                <AlertTriangle className="h-5 w-5 text-red-400" />
                <AlertTitle className="text-red-400 font-semibold">
                  Critical: Total Limit Breached
                </AlertTitle>
                <AlertDescription>
                  Total drawdown ({status.account.totalDrawdownPct}%) has exceeded the{" "}
                  {status.account.totalLimitPct}% limit.
                </AlertDescription>
              </Alert>
            )}
            {status.account.totalDrawdownPct >= 7.0 &&
              status.account.totalDrawdownPct < status.account.totalLimitPct && (
                <Alert className="bg-amber-950/30 border-amber-900/50 text-amber-200">
                  <AlertTriangle className="h-5 w-5 text-amber-400" />
                  <AlertTitle className="text-amber-400 font-semibold">
                    Warning: Total Drawdown
                  </AlertTitle>
                  <AlertDescription>
                    Total drawdown ({status.account.totalDrawdownPct}%) is approaching the{" "}
                    {status.account.totalLimitPct}% limit.
                  </AlertDescription>
                </Alert>
              )}
          </section>
        )}

        {/* ACTIVE mode warning banner */}
        {tradingMode?.mode === "ACTIVE" && (
          <Alert className="bg-orange-950/40 border-orange-700/60 text-orange-100">
            <AlertTriangle className="h-5 w-5 text-orange-400" />
            <AlertTitle className="text-orange-300 font-semibold tracking-wide">
              LIVE TRADING ACTIVE
            </AlertTitle>
            <AlertDescription className="text-orange-200/80 text-xs mt-1">
              Real orders are being sent to MT5. The system is operating with actual funds.
              Switch to PAPER MODE to stop live execution.
            </AlertDescription>
          </Alert>
        )}

        {/* Connection Status Row */}
        <section data-testid="section-connections">
          <h2 className="text-sm font-semibold text-muted-foreground uppercase tracking-wider mb-3 flex items-center gap-2">
            <Server className="h-4 w-4" />
            Connections
          </h2>
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 sm:gap-4">
            {(
              [
                { key: "polygon", label: "Twelve Data" },
                { key: "redis", label: "Cache" },
                { key: "postgres", label: "Postgres" },
                { key: "mt5", label: "MT5" },
              ] as const
            ).map(({ key: service, label }) => {
              if (statusLoading || !status?.polygon) {
                return <Skeleton key={service} className="h-20 rounded-lg" />;
              }
              const conn = status[service as keyof typeof status] as typeof status.polygon | undefined;
              return (
                <Card
                  key={service}
                  className="bg-card/50 border-border/50"
                  data-testid={`card-connection-${service}`}
                >
                  <CardContent className="p-3 sm:p-4 flex flex-col items-center justify-center text-center gap-2">
                    <div className="flex items-center gap-1.5 font-medium text-xs sm:text-sm text-foreground">
                      {conn?.connected ? (
                        <CheckCircle2 className="h-3.5 w-3.5 text-emerald-500" />
                      ) : (
                        <XCircle className="h-3.5 w-3.5 text-red-500" />
                      )}
                      {label}
                    </div>
                    {conn?.latencyMs != null && (
                      <div className="text-[10px] sm:text-xs text-muted-foreground font-mono">
                        {conn.latencyMs}ms
                      </div>
                    )}
                  </CardContent>
                </Card>
              );
            })}
          </div>
        </section>

        {/* API Usage Meters */}
        {usageStats?.openrouter && usageStats?.twelve_data && (
          <section data-testid="section-api-usage">
            <h2 className="text-sm font-semibold text-muted-foreground uppercase tracking-wider mb-3 flex items-center gap-2">
              <Activity className="h-4 w-4" />
              API Usage
            </h2>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
              {/* OpenRouter / Claude */}
              <Card className="bg-card/50 border-border/50">
                <CardContent className="p-4">
                  <div className="flex items-center justify-between mb-2">
                    <div className="flex items-center gap-2">
                      <Brain className="h-4 w-4 text-violet-400" />
                      <span className="text-sm font-medium">OpenRouter</span>
                      <span className="text-[10px] text-muted-foreground font-mono">Claude Sonnet 4.5</span>
                    </div>
                    {usageStats.openrouter.available ? (
                      <CheckCircle2 className="h-3.5 w-3.5 text-emerald-500" />
                    ) : (
                      <XCircle className="h-3.5 w-3.5 text-red-400" />
                    )}
                  </div>
                  {usageStats.openrouter.available && usageStats.openrouter.initial_balance_usd != null ? (
                    <>
                      <Progress
                        value={Math.min(100, ((usageStats.openrouter.initial_balance_usd - (usageStats.openrouter.remaining_usd ?? 0)) / usageStats.openrouter.initial_balance_usd) * 100)}
                        className="h-2 mb-2"
                      />
                      <div className="flex justify-between text-xs text-muted-foreground">
                        <span>Today: <span className="text-foreground font-mono">${(usageStats.openrouter.daily_spent_usd ?? 0).toFixed(4)}</span></span>
                        <span>Remaining: <span className="text-emerald-400 font-mono font-semibold">${(usageStats.openrouter.remaining_usd ?? 0).toFixed(2)}</span></span>
                      </div>
                      <div className="text-[10px] text-muted-foreground mt-1">
                        Total spent: ${(usageStats.openrouter.total_spent_usd ?? 0).toFixed(4)} of ${usageStats.openrouter.initial_balance_usd}
                      </div>
                    </>
                  ) : (
                    <div className="text-xs text-muted-foreground">Unavailable</div>
                  )}
                </CardContent>
              </Card>

              {/* Twelve Data */}
              <Card className="bg-card/50 border-border/50">
                <CardContent className="p-4">
                  <div className="flex items-center justify-between mb-2">
                    <div className="flex items-center gap-2">
                      <BarChart3 className="h-4 w-4 text-blue-400" />
                      <span className="text-sm font-medium">Twelve Data</span>
                      {usageStats.twelve_data.available && usageStats.twelve_data.plan && (
                        <span className="text-[10px] text-muted-foreground font-mono">{usageStats.twelve_data.plan}</span>
                      )}
                    </div>
                    {usageStats.twelve_data.available ? (
                      <CheckCircle2 className="h-3.5 w-3.5 text-emerald-500" />
                    ) : (
                      <XCircle className="h-3.5 w-3.5 text-red-400" />
                    )}
                  </div>
                  {usageStats.twelve_data.available && usageStats.twelve_data.credits_limit != null ? (
                    <>
                      <Progress
                        value={Math.min(100, ((usageStats.twelve_data.credits_used ?? 0) / usageStats.twelve_data.credits_limit) * 100)}
                        className="h-2 mb-2"
                      />
                      <div className="flex justify-between text-xs text-muted-foreground">
                        <span>Used: <span className="text-foreground font-mono">{usageStats.twelve_data.credits_used ?? 0}</span></span>
                        <span>Limit: <span className="font-mono">{usageStats.twelve_data.credits_limit} credits/day</span></span>
                      </div>
                      <div className="text-[10px] text-muted-foreground mt-1">
                        {Math.round(((usageStats.twelve_data.credits_used ?? 0) / usageStats.twelve_data.credits_limit) * 100)}% used today · resets daily
                      </div>
                    </>
                  ) : (
                    <div className="text-xs text-muted-foreground">Unavailable</div>
                  )}
                </CardContent>
              </Card>
            </div>
          </section>
        )}

        {/* AI Ops Dashboard */}
        <section data-testid="section-ai-ops">
          <h2 className="text-sm font-semibold text-muted-foreground uppercase tracking-wider mb-3 flex items-center gap-2">
            <Brain className="h-4 w-4" />
            AI Operations
          </h2>
          <div className="grid grid-cols-1 gap-3">
            {/* Status row */}
            <div className="grid grid-cols-3 gap-2">
              <Card className="bg-card/50 border-border/50">
                <CardContent className="p-3 flex flex-col items-center justify-center text-center gap-1">
                  <div className="text-[10px] text-muted-foreground uppercase tracking-wider">Brain</div>
                  <div className="flex items-center gap-1">
                    {agentService?.online ? (
                      <CheckCircle2 className="h-3.5 w-3.5 text-emerald-500" />
                    ) : (
                      <XCircle className="h-3.5 w-3.5 text-red-400" />
                    )}
                    <span className="text-xs font-medium">
                      {agentService?.online ? "Running" : "Offline"}
                    </span>
                  </div>
                </CardContent>
              </Card>
              <Card className="bg-card/50 border-border/50">
                <CardContent className="p-3 flex flex-col items-center justify-center text-center gap-1">
                  <div className="text-[10px] text-muted-foreground uppercase tracking-wider">Memory</div>
                  <div className="flex items-center gap-1">
                    <CheckCircle2 className="h-3.5 w-3.5 text-emerald-500" />
                    <span className="text-xs font-medium">PostgreSQL</span>
                  </div>
                </CardContent>
              </Card>
              <Card className="bg-card/50 border-border/50">
                <CardContent className="p-3 flex flex-col items-center justify-center text-center gap-1">
                  <div className="text-[10px] text-muted-foreground uppercase tracking-wider">Dominant</div>
                  <span className="text-xs font-semibold text-violet-400 truncate">
                    {strategyScores?.dominant_strategy ?? "—"}
                  </span>
                </CardContent>
              </Card>
            </div>

            {/* Strategy Scores */}
            <Card className="bg-card/50 border-border/50">
              <CardContent className="p-4">
                <div className="flex items-center justify-between mb-3">
                  <span className="text-sm font-medium">Strategy Scores</span>
                  <span className="text-[10px] text-muted-foreground font-mono">
                    last {strategyScores?.window_trades ?? 50} signals
                  </span>
                </div>
                {!strategyScores || (strategyScores?.scores ?? []).length === 0 ? (
                  <div className="text-xs text-muted-foreground text-center py-4">
                    No data yet — scores accumulate with each trade cycle
                  </div>
                ) : (
                  <div className="space-y-2.5">
                    {(strategyScores?.scores ?? []).map((s) => (
                      <div key={s.strategy}>
                        <div className="flex justify-between items-center mb-1">
                          <div className="flex items-center gap-1.5">
                            <span className="text-xs font-medium">{s.strategy}</span>
                            {s.dominant && (
                              <Badge variant="outline" className="text-[9px] px-1 py-0 text-violet-400 border-violet-400/40">
                                top
                              </Badge>
                            )}
                          </div>
                          <div className="flex items-center gap-2 text-[10px] font-mono text-muted-foreground">
                            <span>{s.wins}W / {s.losses}L</span>
                            {s.win_rate != null ? (
                              <span className={s.win_rate >= 0.5 ? "text-emerald-400 font-semibold" : "text-red-400"}>
                                {(s.win_rate * 100).toFixed(0)}%
                              </span>
                            ) : (
                              <span>—</span>
                            )}
                          </div>
                        </div>
                        <Progress
                          value={s.win_rate != null ? s.win_rate * 100 : 0}
                          className="h-1.5"
                        />
                      </div>
                    ))}
                  </div>
                )}
              </CardContent>
            </Card>
          </div>
        </section>

        {/* P&L Counter */}
        <section data-testid="section-pnl">
          <h2 className="text-sm font-semibold text-muted-foreground uppercase tracking-wider mb-3 flex items-center gap-2">
            <TrendingUp className="h-4 w-4" />
            Profit &amp; Loss
          </h2>
          <div className="grid grid-cols-2 gap-3 mb-3">
            {/* Today Realized */}
            <Card className="bg-card/50 border-border/50">
              <CardContent className="p-4">
                <div className="text-xs text-muted-foreground mb-1">Today Realized</div>
                <div className={`text-2xl font-bold font-mono tracking-tight ${(pnlSummary?.today_realized ?? 0) >= 0 ? "text-emerald-400" : "text-red-400"}`}>
                  {(pnlSummary?.today_realized ?? 0) >= 0 ? "+" : ""}
                  {(pnlSummary?.today_realized ?? 0).toFixed(2)}
                </div>
                <div className="text-[10px] text-muted-foreground mt-1">
                  {pnlSummary?.today_trades ?? 0} closed today
                </div>
              </CardContent>
            </Card>

            {/* Total Realized */}
            <Card className="bg-card/50 border-border/50">
              <CardContent className="p-4">
                <div className="text-xs text-muted-foreground mb-1">Total Realized</div>
                <div className={`text-2xl font-bold font-mono tracking-tight ${(pnlSummary?.total_realized ?? 0) >= 0 ? "text-emerald-400" : "text-red-400"}`}>
                  {(pnlSummary?.total_realized ?? 0) >= 0 ? "+" : ""}
                  {(pnlSummary?.total_realized ?? 0).toFixed(2)}
                </div>
                <div className="text-[10px] text-muted-foreground mt-1">
                  {pnlSummary?.total_trades ?? 0} total trades
                </div>
              </CardContent>
            </Card>
          </div>

          {/* Stats row */}
          <Card className="bg-card/50 border-border/50">
            <CardContent className="p-4">
              <div className="grid grid-cols-4 gap-3 text-center">
                <div>
                  <div className="text-[10px] text-muted-foreground uppercase tracking-wider mb-1">Wins</div>
                  <div className="text-lg font-bold text-emerald-400 font-mono">{pnlSummary?.total_wins ?? 0}</div>
                </div>
                <div>
                  <div className="text-[10px] text-muted-foreground uppercase tracking-wider mb-1">Losses</div>
                  <div className="text-lg font-bold text-red-400 font-mono">{pnlSummary?.total_losses ?? 0}</div>
                </div>
                <div>
                  <div className="text-[10px] text-muted-foreground uppercase tracking-wider mb-1">Win Rate</div>
                  <div className={`text-lg font-bold font-mono ${pnlSummary?.win_rate != null && pnlSummary.win_rate >= 0.5 ? "text-emerald-400" : "text-muted-foreground"}`}>
                    {pnlSummary?.win_rate != null ? `${(pnlSummary.win_rate * 100).toFixed(0)}%` : "—"}
                  </div>
                </div>
                <div>
                  <div className="text-[10px] text-muted-foreground uppercase tracking-wider mb-1">Best</div>
                  <div className="text-lg font-bold text-emerald-400 font-mono">
                    {pnlSummary?.best_trade != null ? `+${pnlSummary.best_trade.toFixed(2)}` : "—"}
                  </div>
                </div>
              </div>
              {pnlSummary?.worst_trade != null && (
                <div className="mt-3 pt-3 border-t border-border/30 flex justify-between text-xs text-muted-foreground">
                  <span>Worst trade: <span className="text-red-400 font-mono">{pnlSummary.worst_trade.toFixed(2)}</span></span>
                  <span className="font-mono text-[10px]">Updated {pnlSummary.updated_at ? new Date(pnlSummary.updated_at).toLocaleTimeString() : "—"}</span>
                </div>
              )}
            </CardContent>
          </Card>
        </section>

        {/* Account Metrics Grid */}
        <section data-testid="section-account">
          <h2 className="text-sm font-semibold text-muted-foreground uppercase tracking-wider mb-3 flex items-center gap-2">
            <BarChart3 className="h-4 w-4" />
            Account Metrics
          </h2>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            {statusLoading || !status?.account ? (
              <>
                <Skeleton className="h-24 rounded-lg" />
                <Skeleton className="h-24 rounded-lg" />
                <Skeleton className="h-24 rounded-lg" />
                <Skeleton className="h-24 rounded-lg" />
              </>
            ) : (
              <>
                <Card className="bg-card/50" data-testid="card-balance">
                  <CardContent className="p-4 sm:p-5">
                    <div className="text-sm text-muted-foreground font-medium mb-1">Balance</div>
                    <div className="text-2xl font-bold tracking-tight">
                      {formatCurrency(status.account.balance, status.account.currency)}
                    </div>
                  </CardContent>
                </Card>
                <Card className="bg-card/50" data-testid="card-equity">
                  <CardContent className="p-4 sm:p-5">
                    <div className="text-sm text-muted-foreground font-medium mb-1">Equity</div>
                    <div className="text-2xl font-bold tracking-tight">
                      {formatCurrency(status.account.equity, status.account.currency)}
                    </div>
                  </CardContent>
                </Card>
                <Card className="bg-card/50" data-testid="card-daily-drawdown">
                  <CardContent className="p-4 sm:p-5 space-y-3">
                    <div className="flex justify-between items-center text-sm font-medium">
                      <span className="text-muted-foreground">Daily Drawdown</span>
                      <span
                        className={
                          status.account.dailyDrawdownPct >= status.account.dailyLimitPct
                            ? "text-red-400"
                            : ""
                        }
                      >
                        {status.account.dailyDrawdownPct}% / {status.account.dailyLimitPct}%
                      </span>
                    </div>
                    <Progress
                      value={
                        (status.account.dailyDrawdownPct / status.account.dailyLimitPct) * 100
                      }
                      className="h-2"
                    />
                  </CardContent>
                </Card>
                <Card className="bg-card/50" data-testid="card-total-drawdown">
                  <CardContent className="p-4 sm:p-5 space-y-3">
                    <div className="flex justify-between items-center text-sm font-medium">
                      <span className="text-muted-foreground">Total Drawdown</span>
                      <span
                        className={
                          status.account.totalDrawdownPct >= status.account.totalLimitPct
                            ? "text-red-400"
                            : ""
                        }
                      >
                        {status.account.totalDrawdownPct}% / {status.account.totalLimitPct}%
                      </span>
                    </div>
                    <Progress
                      value={
                        (status.account.totalDrawdownPct / status.account.totalLimitPct) * 100
                      }
                      className="h-2"
                    />
                  </CardContent>
                </Card>
              </>
            )}
          </div>
        </section>

        {/* Active Positions */}
        <section data-testid="section-trades">
          <h2 className="text-sm font-semibold text-muted-foreground uppercase tracking-wider mb-3 flex items-center gap-2">
            <ChevronsUpDown className="h-4 w-4" />
            Active Positions
            {trades && trades.length > 0 && (
              <Badge variant="outline" className="ml-auto text-[10px] px-1.5 py-0 font-mono">
                {trades.length} open
              </Badge>
            )}
          </h2>

          <div className="space-y-3">
            {tradesLoading ? (
              <>
                <Skeleton className="h-28 rounded-lg" />
                <Skeleton className="h-28 rounded-lg" />
              </>
            ) : trades && trades.length > 0 ? (
              trades.map((trade) => (
                <Card
                  key={trade.id}
                  className="bg-card/50 border-border/50 overflow-hidden"
                  data-testid={`card-trade-${trade.id}`}
                >
                  <CardContent className="p-0">
                    {/* Top row: symbol + direction + P&L */}
                    <div className="flex items-center justify-between px-4 pt-3 pb-2">
                      <div className="flex items-center gap-2">
                        <span className="font-bold text-base tracking-tight">{trade.symbol}</span>
                        <Badge
                          variant="outline"
                          className={`text-[10px] px-1.5 py-0 font-mono ${
                            trade.direction === "BUY"
                              ? "bg-emerald-500/10 text-emerald-400 border-emerald-500/30"
                              : "bg-red-500/10 text-red-400 border-red-500/30"
                          }`}
                        >
                          {trade.direction === "BUY" ? (
                            <TrendingUp className="h-2.5 w-2.5 mr-0.5 inline" />
                          ) : (
                            <TrendingDown className="h-2.5 w-2.5 mr-0.5 inline" />
                          )}
                          {trade.direction}
                        </Badge>
                        <Badge
                          variant="outline"
                          className={`text-[10px] px-1.5 py-0 ${
                            trade.source === "MANUAL"
                              ? "text-purple-400 border-purple-500/30"
                              : "text-blue-400 border-blue-500/30"
                          }`}
                        >
                          {trade.source}
                        </Badge>
                      </div>
                      <div className="text-right">
                        <div
                          className={`text-base font-bold font-mono ${
                            trade.pnl >= 0 ? "text-emerald-400" : "text-red-400"
                          }`}
                        >
                          {trade.pnl >= 0 ? "+" : ""}
                          {trade.pnl.toFixed(2)}
                        </div>
                        <div
                          className={`text-[10px] font-mono ${
                            trade.pnl >= 0 ? "text-emerald-500/70" : "text-red-500/70"
                          }`}
                        >
                          {trade.pnlPct >= 0 ? "+" : ""}
                          {trade.pnlPct.toFixed(2)}%
                        </div>
                      </div>
                    </div>

                    {/* Price details */}
                    <div className="grid grid-cols-3 gap-2 px-4 py-2 bg-secondary/20 text-xs text-muted-foreground">
                      <div>
                        <div className="text-[10px] uppercase mb-0.5">Open</div>
                        <div className="font-mono text-foreground/80">{trade.openPrice}</div>
                      </div>
                      <div>
                        <div className="text-[10px] uppercase mb-0.5">Current</div>
                        <div className="font-mono text-foreground/80">{trade.currentPrice}</div>
                      </div>
                      <div>
                        <div className="text-[10px] uppercase mb-0.5">Size</div>
                        <div className="font-mono text-foreground/80">{trade.lots} lots</div>
                      </div>
                    </div>

                    {/* SL/TP + Actions */}
                    <div className="flex items-center justify-between px-4 py-2.5 gap-2">
                      <div className="flex items-center gap-3 text-[10px] text-muted-foreground font-mono">
                        {trade.stopLoss != null && (
                          <span>
                            SL:{" "}
                            <span className="text-red-400/80">{trade.stopLoss}</span>
                          </span>
                        )}
                        {trade.takeProfit != null && (
                          <span>
                            TP:{" "}
                            <span className="text-emerald-400/80">{trade.takeProfit}</span>
                          </span>
                        )}
                        <span className="text-muted-foreground/60">
                          {formatDistanceToNow(new Date(trade.openedAt), { addSuffix: true })}
                        </span>
                      </div>
                      <div className="flex items-center gap-2 shrink-0">
                        <Button
                          variant="outline"
                          size="sm"
                          className="h-7 px-2.5 text-xs gap-1 border-blue-500/30 text-blue-400 hover:bg-blue-500/10 hover:text-blue-300"
                          onClick={() =>
                            setIncreaseTarget({
                              id: trade.id,
                              symbol: trade.symbol,
                              direction: trade.direction,
                              lots: trade.lots,
                            })
                          }
                        >
                          <Plus className="h-3 w-3" />
                          Add
                        </Button>
                        <Button
                          variant="outline"
                          size="sm"
                          className="h-7 px-2.5 text-xs gap-1 border-red-500/30 text-red-400 hover:bg-red-500/10 hover:text-red-300"
                          onClick={() =>
                            setCloseTarget({
                              id: trade.id,
                              symbol: trade.symbol,
                              pnl: trade.pnl,
                            })
                          }
                        >
                          <X className="h-3 w-3" />
                          Close
                        </Button>
                      </div>
                    </div>
                  </CardContent>
                </Card>
              ))
            ) : (
              <div className="text-sm text-muted-foreground italic p-6 text-center border rounded-lg bg-card/20">
                No open positions.
              </div>
            )}
          </div>
        </section>

        {/* Sentiment Analysis */}
        <section data-testid="section-sentiment">
          <h2 className="text-sm font-semibold text-muted-foreground uppercase tracking-wider mb-3 flex items-center gap-2">
            <Brain className="h-4 w-4" />
            Sentiment Analysis
          </h2>

          {sentimentLoading ? (
            <div className="space-y-3">
              <Skeleton className="h-20 rounded-xl" />
              <Skeleton className="h-32 rounded-xl" />
              <Skeleton className="h-32 rounded-xl" />
            </div>
          ) : sentiment?.overallScore != null ? (
            <div className="space-y-3">
              <Card className="bg-card/50 border-border/50" data-testid="card-sentiment-overall">
                <CardContent className="p-4 sm:p-5 space-y-3">
                  <div className="flex items-center justify-between">
                    <span className="text-sm font-medium text-muted-foreground">
                      Overall Market Sentiment
                    </span>
                    <SentimentBadge label={sentiment.overallSentiment as SentimentLabel} />
                  </div>
                  <ScoreBar score={sentiment.overallScore} />
                  <p className="text-[10px] text-muted-foreground text-right font-mono">
                    Score: {(sentiment.overallScore ?? 0) > 0 ? "+" : ""}
                    {(sentiment.overallScore ?? 0).toFixed(3)}
                  </p>
                </CardContent>
              </Card>

              <Card className="bg-card/50 border-border/50" data-testid="card-articles">
                <CardHeader className="p-4 pb-2">
                  <CardTitle className="text-xs font-semibold flex items-center justify-between">
                    <span className="flex items-center gap-1.5">
                      <Brain className="h-3.5 w-3.5 text-purple-400" />
                      GPT-4o — Article Sentiment
                    </span>
                    <Badge
                      variant="outline"
                      className={`text-[10px] px-1.5 py-0 ${
                        sentiment.source === "polygon+gpt"
                          ? "text-emerald-400 border-emerald-500/30"
                          : "text-amber-400 border-amber-500/30"
                      }`}
                    >
                      {sentiment.source === "polygon+gpt" ? "Live" : "Demo"}
                    </Badge>
                  </CardTitle>
                </CardHeader>
                <CardContent className="p-4 pt-0 space-y-2">
                  {(sentiment.articles ?? []).slice(0, 5).map((a) => (
                    <div
                      key={a.id}
                      className="flex items-start justify-between gap-2 text-xs py-1.5 border-b border-border/30 last:border-0"
                      data-testid={`row-article-${a.id}`}
                    >
                      <span className="text-muted-foreground line-clamp-1 flex-1">{a.title}</span>
                      <div className="flex items-center gap-1.5 shrink-0">
                        <SentimentBadge label={a.sentiment as SentimentLabel} />
                        <span className="text-[10px] font-mono text-muted-foreground w-8 text-right">
                          {(a.score * 100).toFixed(0)}%
                        </span>
                      </div>
                    </div>
                  ))}
                </CardContent>
              </Card>
            </div>
          ) : (
            <div className="text-sm text-muted-foreground italic p-4 text-center border rounded-lg bg-card/20">
              Sentiment data unavailable.
            </div>
          )}
        </section>

        {/* Latest News */}
        <section data-testid="section-news">
          <h2 className="text-sm font-semibold text-muted-foreground uppercase tracking-wider mb-3 flex items-center gap-2">
            <Newspaper className="h-4 w-4" />
            Market News
          </h2>
          <div className="space-y-3">
            {newsLoading ? (
              <>
                <Skeleton className="h-16 rounded-lg" />
                <Skeleton className="h-16 rounded-lg" />
                <Skeleton className="h-16 rounded-lg" />
              </>
            ) : Array.isArray(news) && news.length > 0 ? (
              news.slice(0, 5).map((item) => (
                <Card
                  key={item.id}
                  className="bg-card/50 overflow-hidden"
                  data-testid={`card-news-${item.id}`}
                >
                  <CardContent className="p-3 sm:p-4">
                    <div className="flex justify-between items-start gap-3 mb-2">
                      <h3 className="text-sm font-medium leading-snug line-clamp-2">
                        {item.title}
                      </h3>
                      <Badge
                        variant="secondary"
                        className={`shrink-0 text-[10px] px-1.5 py-0 rounded ${
                          item.impact === "HIGH"
                            ? "bg-red-500/10 text-red-400 border-red-500/20"
                            : item.impact === "MEDIUM"
                            ? "bg-amber-500/10 text-amber-400 border-amber-500/20"
                            : "bg-muted text-muted-foreground"
                        }`}
                      >
                        {item.impact}
                      </Badge>
                    </div>
                    <div className="flex items-center justify-between text-xs text-muted-foreground">
                      <div className="flex items-center gap-2">
                        <span className="font-medium text-foreground/70">{item.source}</span>
                        {item.currency && (
                          <Badge
                            variant="outline"
                            className="text-[10px] px-1 h-4 bg-transparent"
                          >
                            {item.currency}
                          </Badge>
                        )}
                      </div>
                      <span className="shrink-0">
                        {formatDistanceToNow(new Date(item.publishedAt), { addSuffix: true })}
                      </span>
                    </div>
                  </CardContent>
                </Card>
              ))
            ) : (
              <div className="text-sm text-muted-foreground italic p-4 text-center border rounded-lg bg-card/20">
                No recent news available.
              </div>
            )}
          </div>
        </section>

        {/* Python Agent Engine */}
        <section data-testid="section-agent-engine">
          <h2 className="text-sm font-semibold text-muted-foreground uppercase tracking-wider mb-3 flex items-center gap-2">
            <Bot className="h-4 w-4" />
            Agent Engine
          </h2>
          <Card className="bg-card/50 border-border/50">
            <CardContent className="p-4 space-y-4">
              {/* Service status row */}
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <span className="relative flex h-2 w-2">
                    {agentService?.online ? (
                      <>
                        <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75" />
                        <span className="relative inline-flex rounded-full h-2 w-2 bg-emerald-500" />
                      </>
                    ) : (
                      <span className="relative inline-flex rounded-full h-2 w-2 bg-red-500" />
                    )}
                  </span>
                  <span className="text-xs font-medium text-foreground">
                    {agentService?.online
                      ? "Python Agents Online"
                      : agentService?.configured === false
                      ? "Brain Server Not Configured"
                      : agentService?.reason === "timeout"
                      ? "Brain Server Unreachable (Timeout)"
                      : "Python Agents Offline"}
                  </span>
                </div>
                {agentService?.online ? (
                  <Badge variant="outline" className="text-[10px] px-1.5 py-0 text-blue-400 border-blue-500/30">
                    {(agentService?.info as {mode?: string} | undefined)?.mode ?? "PAPER_MODE"}
                  </Badge>
                ) : agentService?.target ? (
                  <Badge variant="outline" className="text-[10px] px-1.5 py-0 text-red-400 border-red-500/30 font-mono">
                    {agentService.target}
                  </Badge>
                ) : null}
              </div>

              {/* Run Cycle button */}
              <button
                onClick={async () => {
                  try {
                    await runCycleMutation.mutateAsync({ data: { dry_run: true } });
                    setTimeout(() => refetchCycle(), 3000);
                    setTimeout(() => refetchCycle(), 8000);
                    setLastActionMsg("Agent cycle triggered — analyzing EURUSD, GBPUSD, USDJPY, XAUUSD...");
                  } catch {
                    setLastActionMsg("Failed to trigger cycle — Python agent service may be offline.");
                  }
                }}
                disabled={!agentService?.online || runCycleMutation.isPending}
                className={`w-full py-2.5 px-4 rounded-lg text-sm font-semibold transition-all flex items-center justify-center gap-2 ${
                  agentService?.online && !runCycleMutation.isPending
                    ? "bg-primary text-primary-foreground hover:bg-primary/90"
                    : "bg-secondary text-muted-foreground cursor-not-allowed"
                }`}
              >
                <Radio className={`h-4 w-4 ${runCycleMutation.isPending ? "animate-pulse" : ""}`} />
                {runCycleMutation.isPending ? "Running Cycle..." : "Run Agent Cycle"}
              </button>

              {/* Latest cycle result */}
              {cycleStatus && (
                <div className="border border-border/40 rounded-lg p-3 space-y-2 bg-background/30">
                  <div className="flex items-center justify-between text-xs">
                    <span className="text-muted-foreground font-mono">
                      Cycle #{cycleStatus.cycle_id}
                    </span>
                    <Badge
                      variant="outline"
                      className={`text-[10px] px-1.5 py-0 ${
                        cycleStatus.status === "completed"
                          ? "text-emerald-400 border-emerald-500/30"
                          : cycleStatus.status === "running"
                          ? "text-blue-400 border-blue-500/30 animate-pulse"
                          : "text-red-400 border-red-500/30"
                      }`}
                    >
                      {cycleStatus.status}
                    </Badge>
                  </div>

                  {cycleStatus.decision && (
                    <div className="flex items-center justify-between">
                      <div className="flex items-center gap-2">
                        <Badge
                          variant="outline"
                          className={`text-xs font-bold px-2 py-0.5 ${
                            cycleStatus.decision.action === "BUY"
                              ? "bg-emerald-500/10 text-emerald-400 border-emerald-500/30"
                              : cycleStatus.decision.action === "SELL"
                              ? "bg-red-500/10 text-red-400 border-red-500/30"
                              : "bg-secondary text-muted-foreground"
                          }`}
                        >
                          {cycleStatus.decision.action}
                        </Badge>
                        {cycleStatus.decision.symbol && cycleStatus.decision.symbol !== "N/A" && (
                          <span className="text-xs font-mono text-foreground">
                            {cycleStatus.decision.symbol}
                          </span>
                        )}
                      </div>
                      <span className="text-[10px] text-muted-foreground font-mono">
                        {Math.round((cycleStatus.decision.confidence ?? 0) * 100)}% confidence
                      </span>
                    </div>
                  )}

                  {cycleStatus.decision?.reasoning && (
                    <p className="text-[11px] text-muted-foreground leading-relaxed line-clamp-2">
                      {cycleStatus.decision.reasoning}
                    </p>
                  )}

                  <div className="flex items-center justify-between text-[10px] text-muted-foreground">
                    <span>{(cycleStatus.symbols_analyzed ?? []).join(", ")}</span>
                    {cycleStatus.duration_ms && (
                      <span className="font-mono">{cycleStatus.duration_ms}ms</span>
                    )}
                  </div>
                </div>
              )}

              {!agentService?.online && (
                <div className="border border-red-500/30 bg-red-500/5 rounded-lg p-3 space-y-1">
                  <p className="text-[11px] font-medium text-red-400 text-center">
                    {agentService?.message ??
                      "Start the Python Agent Service workflow to enable LangGraph agents."}
                  </p>
                  {agentService?.target && (
                    <p className="text-[10px] text-muted-foreground text-center font-mono">
                      target: {agentService.target}
                      {agentService.reason ? ` · ${agentService.reason}` : ""}
                    </p>
                  )}
                </div>
              )}
            </CardContent>
          </Card>
        </section>

        {/* Trading Controls — Mode Switch + Scheduler */}
        <section data-testid="section-trading-controls">
          <h2 className="text-sm font-semibold text-muted-foreground uppercase tracking-wider mb-3 flex items-center gap-2">
            <Zap className="h-4 w-4" />
            Trading Controls
          </h2>
          <Card className="bg-card/50 border-border/50">
            <CardContent className="p-4 space-y-5">

              {/* Mode selector */}
              <div className="space-y-2">
                <div className="text-xs font-semibold text-muted-foreground uppercase tracking-wider">
                  Execution Mode
                </div>
                <div className="grid grid-cols-3 gap-2">
                  {(["PAPER_MODE", "ACTIVE", "FROZEN"] as const).map((m) => {
                    const current = tradingMode?.mode ?? "PAPER_MODE";
                    const isCurrent = current === m;
                    const cfg = {
                      PAPER_MODE: { label: "Paper", cls: "border-blue-500/40 text-blue-400 bg-blue-500/10", active: "border-blue-500 bg-blue-500/20" },
                      ACTIVE:     { label: "Active", cls: "border-emerald-500/40 text-emerald-400 bg-emerald-500/10", active: "border-emerald-500 bg-emerald-500/20" },
                      FROZEN:     { label: "Frozen", cls: "border-red-500/40 text-red-400 bg-red-500/10", active: "border-red-500 bg-red-500/20" },
                    }[m];
                    return (
                      <button
                        key={m}
                        disabled={isCurrent || setModeMutation.isPending}
                        onClick={() => {
                          if (m === "ACTIVE" || m === "FROZEN") {
                            setModeConfirm(m);
                          } else {
                            setModeMutation.mutate(
                              { data: { mode: m } },
                              { onSuccess: () => { refetchMode(); setLastActionMsg(`Mode changed to ${m}`); } }
                            );
                          }
                        }}
                        className={`py-2 px-3 rounded-lg border text-xs font-semibold transition-all ${
                          isCurrent ? cfg.active + " ring-1 ring-inset ring-current" : cfg.cls + " hover:opacity-80"
                        } disabled:opacity-50 disabled:cursor-not-allowed`}
                      >
                        {cfg.label}
                        {isCurrent && <span className="block text-[9px] opacity-70 mt-0.5">current</span>}
                      </button>
                    );
                  })}
                </div>
                {tradingMode?.mode === "ACTIVE" && (
                  <p className="text-[10px] text-emerald-400/80 flex items-center gap-1">
                    <ShieldCheck className="h-3 w-3" />
                    Live trading active — real orders will be sent to MT5
                  </p>
                )}
                {tradingMode?.mode === "FROZEN" && (
                  <p className="text-[10px] text-red-400/80 flex items-center gap-1">
                    <ShieldAlert className="h-3 w-3" />
                    System frozen — no orders will be executed
                  </p>
                )}
              </div>

              <div className="border-t border-border/40" />

              {/* Auto-cycle scheduler */}
              <div className="space-y-3">
                <div className="flex items-center justify-between">
                  <div>
                    <div className="text-xs font-semibold text-foreground flex items-center gap-1.5">
                      <Timer className="h-3.5 w-3.5 text-muted-foreground" />
                      Auto-Cycle Scheduler
                    </div>
                    <div className="text-[10px] text-muted-foreground mt-0.5">
                      {schedulerStatus?.running
                        ? `Running — every ${schedulerStatus.interval_minutes} min (${schedulerStatus.cycles_completed} completed)`
                        : "Stopped — trigger cycles manually"}
                    </div>
                  </div>
                  <Switch
                    checked={!!schedulerStatus?.running}
                    disabled={startSchedulerMutation.isPending || stopSchedulerMutation.isPending}
                    onCheckedChange={async (checked) => {
                      if (checked) {
                        const mins = parseInt(schedulerInterval) || 30;
                        await startSchedulerMutation.mutateAsync({ data: { interval_minutes: mins } });
                        refetchScheduler();
                        setLastActionMsg(`Scheduler started — cycle every ${mins} minutes`);
                      } else {
                        await stopSchedulerMutation.mutateAsync(undefined);
                        refetchScheduler();
                        setLastActionMsg("Scheduler stopped");
                      }
                    }}
                  />
                </div>
                {!schedulerStatus?.running && (
                  <div className="flex items-center gap-2">
                    <Input
                      type="number"
                      min="1"
                      max="1440"
                      value={schedulerInterval}
                      onChange={(e) => setSchedulerInterval(e.target.value)}
                      className="h-7 text-xs font-mono w-20"
                      placeholder="30"
                    />
                    <span className="text-xs text-muted-foreground">minutes per cycle</span>
                  </div>
                )}
                {schedulerStatus?.last_run && (
                  <div className="text-[10px] text-muted-foreground">
                    Last run: {formatDistanceToNow(new Date(schedulerStatus.last_run), { addSuffix: true })}
                  </div>
                )}
              </div>
            </CardContent>
          </Card>
        </section>

        {/* Live Positions */}
        {((livePositions?.count ?? 0) > 0 || livePositions?.source === "mt5_live") && (
          <section data-testid="section-live-positions">
            <h2 className="text-sm font-semibold text-muted-foreground uppercase tracking-wider mb-3 flex items-center gap-2">
              <ArrowUpCircle className="h-4 w-4" />
              Open Positions
              {livePositions?.source === "mt5_live" && (
                <Badge variant="outline" className="text-[9px] px-1.5 py-0 text-emerald-400 border-emerald-500/30">
                  LIVE
                </Badge>
              )}
            </h2>
            <div className="space-y-2">
              {livePositions?.account && (
                <div className="grid grid-cols-3 gap-2 mb-3">
                  {(() => {
                    const acc = livePositions.account as { currency?: string; balance?: number; equity?: number; profit?: number };
                    const profit = acc.profit ?? 0;
                    return [
                      { label: "Balance", val: `${acc.currency ?? ""} ${acc.balance?.toLocaleString() ?? "—"}` },
                      { label: "Equity",  val: `${acc.equity?.toLocaleString() ?? "—"}` },
                      { label: "P&L",     val: `${profit >= 0 ? "+" : ""}${profit.toFixed(2)}` },
                    ];
                  })().map(({ label, val }) => (
                    <Card key={label} className="bg-card/30">
                      <CardContent className="p-2 text-center">
                        <div className="text-[10px] text-muted-foreground">{label}</div>
                        <div className="text-xs font-mono font-semibold">{val}</div>
                      </CardContent>
                    </Card>
                  ))}
                </div>
              )}
              {(livePositions?.positions ?? []).length === 0 ? (
                <div className="text-sm text-muted-foreground italic p-4 text-center border rounded-lg bg-card/20">
                  No open positions.
                </div>
              ) : (
                (livePositions?.positions ?? []).map((pos) => {
                  const posId = String(pos.ticket ?? `${pos.symbol}-${pos.type}`);
                  return (
                    <Card key={posId} className="bg-card/50 border-border/50">
                      <CardContent className="p-3 space-y-2">
                        <div className="flex items-center justify-between">
                          <div className="flex items-center gap-2">
                            <Badge
                              variant="outline"
                              className={`text-xs font-bold px-2 py-0.5 ${
                                pos.type === "BUY"
                                  ? "bg-emerald-500/10 text-emerald-400 border-emerald-500/30"
                                  : "bg-red-500/10 text-red-400 border-red-500/30"
                              }`}
                            >
                              {pos.type}
                            </Badge>
                            <span className="text-sm font-mono font-semibold">{pos.symbol}</span>
                            <span className="text-xs text-muted-foreground">{pos.volume} lots</span>
                          </div>
                          <span
                            className={`text-sm font-mono font-bold ${
                              (pos.profit ?? 0) >= 0 ? "text-emerald-400" : "text-red-400"
                            }`}
                          >
                            {(pos.profit ?? 0) >= 0 ? "+" : ""}
                            {(pos.profit ?? 0).toFixed(2)}
                          </span>
                        </div>
                        <div className="flex items-center justify-between text-[10px] text-muted-foreground font-mono">
                          <span>Open: {pos.open_price}</span>
                          {pos.current_price && <span>Now: {pos.current_price}</span>}
                          {pos.sl ? <span>SL: {pos.sl}</span> : null}
                        </div>
                        <button
                          onClick={() => setAgentCloseTarget({ id: posId, symbol: pos.symbol, profit: pos.profit ?? 0 })}
                          className="w-full py-1.5 text-xs font-semibold rounded border border-red-500/30 text-red-400 hover:bg-red-500/10 transition-colors"
                        >
                          Close Position
                        </button>
                      </CardContent>
                    </Card>
                  );
                })
              )}
            </div>
          </section>
        )}

        {/* Agent Decisions Log */}
        <section data-testid="section-agent-log">
          <h2 className="text-sm font-semibold text-muted-foreground uppercase tracking-wider mb-3 flex items-center gap-2">
            <Bot className="h-4 w-4" />
            Agent Log
          </h2>
          <div className="space-y-3 relative before:absolute before:inset-0 before:ml-5 before:-translate-x-px md:before:mx-auto md:before:translate-x-0 before:h-full before:w-0.5 before:bg-border/50">
            {decisionsLoading ? (
              <>
                <Skeleton className="h-24 rounded-lg ml-12 md:ml-0" />
                <Skeleton className="h-24 rounded-lg ml-12 md:ml-0" />
              </>
            ) : Array.isArray(decisions) && decisions.length > 0 ? (
              decisions.slice(0, 5).map((decision) => (
                <div
                  key={decision.id}
                  className="relative flex items-start gap-4"
                  data-testid={`row-decision-${decision.id}`}
                >
                  <div className="absolute left-0 md:left-1/2 flex h-10 w-10 items-center justify-center -translate-x-1/2 rounded-full border border-background bg-card">
                    <div
                      className={`h-3 w-3 rounded-full ${
                        decision.approved === true
                          ? "bg-emerald-500"
                          : decision.approved === false
                          ? "bg-red-500"
                          : "bg-blue-500"
                      }`}
                    />
                  </div>
                  <div className="ml-12 md:ml-0 w-full md:w-1/2 md:even:ml-auto md:odd:mr-auto md:even:pl-8 md:odd:pr-8">
                    <Card
                      className={`bg-card/50 overflow-hidden border-l-2 ${
                        decision.approved === true
                          ? "border-l-emerald-500"
                          : decision.approved === false
                          ? "border-l-red-500"
                          : "border-l-blue-500"
                      }`}
                    >
                      <CardContent className="p-3 sm:p-4 space-y-2">
                        <div className="flex items-center justify-between gap-2">
                          <span className="text-xs font-semibold text-muted-foreground flex items-center gap-1">
                            <Bot className="h-3 w-3" />
                            {decision.agent}
                          </span>
                          <span className="text-[10px] text-muted-foreground shrink-0">
                            {formatDistanceToNow(new Date(decision.timestamp), {
                              addSuffix: true,
                            })}
                          </span>
                        </div>
                        <p className="text-sm font-medium leading-snug">{decision.decision}</p>
                        <p className="text-xs text-muted-foreground leading-relaxed">
                          {decision.reason}
                        </p>
                      </CardContent>
                    </Card>
                  </div>
                </div>
              ))
            ) : (
              <div className="text-sm text-muted-foreground italic p-4 text-center border rounded-lg bg-card/20">
                No agent decisions logged yet.
              </div>
            )}
          </div>
        </section>
      </main>
        </TabsContent>

        <TabsContent value="charts" className="mt-0 focus-visible:outline-none focus-visible:ring-0">
          <Charts />
        </TabsContent>

        <TabsContent value="terminal" className="mt-0 focus-visible:outline-none focus-visible:ring-0">
          <Terminal />
        </TabsContent>

        <TabsContent value="stack" className="mt-0 focus-visible:outline-none focus-visible:ring-0">
          <SystemStack />
        </TabsContent>

        <TabsContent value="accounts" className="mt-0 focus-visible:outline-none focus-visible:ring-0">
          <Accounts />
        </TabsContent>

        <TabsContent value="tools" className="mt-0 focus-visible:outline-none focus-visible:ring-0">
          <Tools />
        </TabsContent>
      </Tabs>

      {/* Dialogs */}
      <CloseConfirmDialog
        tradeId={closeTarget?.id ?? null}
        symbol={closeTarget?.symbol ?? ""}
        pnl={closeTarget?.pnl ?? 0}
        onConfirm={handleCloseConfirm}
        onCancel={() => setCloseTarget(null)}
        isPending={closeMutation.isPending}
      />

      <IncreasePositionDialog
        tradeId={increaseTarget?.id ?? null}
        symbol={increaseTarget?.symbol ?? ""}
        direction={increaseTarget?.direction ?? "BUY"}
        currentLots={increaseTarget?.lots ?? 0}
        onConfirm={handleIncreaseConfirm}
        onCancel={() => setIncreaseTarget(null)}
        isPending={increaseMutation.isPending}
      />

      {/* Mode confirmation dialog */}
      <AlertDialog open={!!modeConfirm}>
        <AlertDialogContent className="bg-card border-border max-w-sm mx-4">
          <AlertDialogHeader>
            <AlertDialogTitle>
              {modeConfirm === "ACTIVE" ? "Enable Live Trading?" : "Freeze System?"}
            </AlertDialogTitle>
            <AlertDialogDescription className="space-y-2">
              {modeConfirm === "ACTIVE" ? (
                <>
                  <span className="block text-amber-400 font-semibold">
                    Real orders will be sent to MetaTrader 5.
                  </span>
                  <span className="block">
                    Ensure MT5 bridge or credentials are configured. The agent pipeline will
                    execute live trades using real account funds.
                  </span>
                </>
              ) : (
                <span className="block">
                  The system will be frozen — no new orders will be executed until you
                  switch back to Paper or Active mode.
                </span>
              )}
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel
              onClick={() => setModeConfirm(null)}
              disabled={setModeMutation.isPending}
            >
              Cancel
            </AlertDialogCancel>
            <AlertDialogAction
              disabled={setModeMutation.isPending}
              onClick={async () => {
                if (!modeConfirm) return;
                try {
                  await setModeMutation.mutateAsync({ data: { mode: modeConfirm } });
                  refetchMode();
                  setLastActionMsg(`Mode changed to ${modeConfirm}`);
                } catch (err: unknown) {
                  const msg = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail;
                  setLastActionMsg(`Failed: ${msg ?? "Check MT5 configuration"}`);
                }
                setModeConfirm(null);
              }}
              className={
                modeConfirm === "ACTIVE"
                  ? "bg-emerald-600 hover:bg-emerald-700 text-white"
                  : "bg-red-600 hover:bg-red-700 text-white"
              }
            >
              {setModeMutation.isPending
                ? "Switching..."
                : modeConfirm === "ACTIVE"
                ? "Enable Live Trading"
                : "Freeze System"}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>

      {/* Agent position close dialog */}
      <AlertDialog open={!!agentCloseTarget}>
        <AlertDialogContent className="bg-card border-border max-w-sm mx-4">
          <AlertDialogHeader>
            <AlertDialogTitle>Close {agentCloseTarget?.symbol} Position?</AlertDialogTitle>
            <AlertDialogDescription className="space-y-1">
              <span className="block">This will close the position via MT5.</span>
              {agentCloseTarget && (
                <span
                  className={`block font-semibold ${
                    agentCloseTarget.profit >= 0 ? "text-emerald-400" : "text-red-400"
                  }`}
                >
                  Current P&L: {agentCloseTarget.profit >= 0 ? "+" : ""}
                  {agentCloseTarget.profit.toFixed(2)}
                </span>
              )}
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel
              onClick={() => setAgentCloseTarget(null)}
              disabled={closeAgentPositionMutation.isPending}
            >
              Cancel
            </AlertDialogCancel>
            <AlertDialogAction
              disabled={closeAgentPositionMutation.isPending}
              onClick={async () => {
                if (!agentCloseTarget) return;
                await closeAgentPositionMutation.mutateAsync({ tradeId: agentCloseTarget.id });
                setAgentCloseTarget(null);
                refetchPositions();
                setLastActionMsg(`Position ${agentCloseTarget.symbol} closed`);
              }}
              className="bg-red-600 hover:bg-red-700 text-white"
            >
              {closeAgentPositionMutation.isPending ? "Closing..." : "Close Position"}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
}
