# Matrix Robot — إصلاح dashboard.tsx دفعة واحدة على VPS (شغّل مرة واحدة)
$path = "C:\MatrixRobot\MatrixRobot\MatrixRobot\artifacts\dashboard\src\pages\dashboard.tsx"
if (-not (Test-Path $path)) {
  Write-Host "لم يُعثر على الملف: $path" -ForegroundColor Red
  exit 1
}

Copy-Item $path "$path.bak-$(Get-Date -Format 'yyyyMMdd-HHmmss')"
$content = Get-Content $path -Raw

$replacements = @(
  @{
    Old = '{status.tradingState.replace("_", " ")}'
    New = '{(status.tradingState ?? "PAPER_MODE").replace(/_/g, " ")}'
  },
  @{
    Old = @"
        {status && (
          <section className="flex flex-col gap-3" data-testid="section-alerts">
"@
    New = @"
        {status?.account && (
          <section className="flex flex-col gap-3" data-testid="section-alerts">
"@
  },
  @{
    Old = '            {statusLoading || !status ? ('
    New = '            {statusLoading || !status?.account ? ('
  },
  @{
    Old = @"
              if (statusLoading || !status) {
                return <Skeleton key={service} className="h-20 rounded-lg" />;
              }
              const conn = status[service as keyof typeof status] as typeof status.polygon;
"@
    New = @"
              if (statusLoading || !status?.polygon) {
                return <Skeleton key={service} className="h-20 rounded-lg" />;
              }
              const conn = status[service as keyof typeof status] as typeof status.polygon;
              if (!conn) {
                return <Skeleton key={service} className="h-20 rounded-lg" />;
              }
"@
  },
  @{
    Old = '        {usageStats && ('
    New = '        {usageStats?.openrouter && usageStats?.twelve_data && ('
  },
  @{
    Old = @"
  const { data: trades, isLoading: tradesLoading } = useGetActiveTrades({
    query: { refetchInterval: 10000, queryKey: getGetActiveTradesQueryKey() },
  });
"@
    New = @"
  const { data: tradesRaw, isLoading: tradesLoading } = useGetActiveTrades({
    query: { refetchInterval: 10000, queryKey: getGetActiveTradesQueryKey() },
  });
  const trades = Array.isArray(tradesRaw) ? tradesRaw : [];
"@
  }
)

$changed = 0
foreach ($r in $replacements) {
  if ($content.Contains($r.Old)) {
    $content = $content.Replace($r.Old, $r.New)
    $changed++
  }
}

Set-Content -Path $path -Value $content -NoNewline
Write-Host "تم — طُبّق $changed تعديلاً. نسخة احتياطية بجانب الملف." -ForegroundColor Green
Write-Host "في Edge: F5 على http://localhost:5173" -ForegroundColor Cyan
