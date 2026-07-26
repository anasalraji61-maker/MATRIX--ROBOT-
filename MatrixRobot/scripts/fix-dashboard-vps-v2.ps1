# Matrix Robot — إصلاح dashboard.tsx v2 (شغّل مرة واحدة على VPS)
$path = "C:\MatrixRobot\MatrixRobot\MatrixRobot\artifacts\dashboard\src\pages\dashboard.tsx"
if (-not (Test-Path $path)) { Write-Host "File not found: $path" -ForegroundColor Red; exit 1 }

Copy-Item $path "$path.bak-v2" -Force
$c = Get-Content $path -Raw

$pairs = @(
  @('{status.tradingState.replace("_", " ")}', '{(status.tradingState ?? "PAPER_MODE").replace(/_/g, " ")}'),
  @('{status && (', '{status?.account && ('),
  @('{statusLoading || !status ? (', '{statusLoading || !status?.account ? ('),
  @('if (statusLoading || !status) {', 'if (statusLoading || !status?.polygon) {'),
  @('{usageStats && (', '{usageStats?.openrouter && usageStats?.twelve_data && ('),
  @(') : sentiment ? (', ') : sentiment?.overallScore != null ? ('),
  @('{sentiment.overallScore > 0 ? "+" : ""}', '{(sentiment.overallScore ?? 0) > 0 ? "+" : ""}'),
  @('{sentiment.overallScore.toFixed(3)}', '{(sentiment.overallScore ?? 0).toFixed(3)}'),
  @('sentiment.articles.slice', '(sentiment.articles ?? []).slice'),
  @('strategyScores.scores.length', '(strategyScores?.scores ?? []).length'),
  @('strategyScores.scores.map', '(strategyScores?.scores ?? []).map'),
  @('{pnlSummary.worst_trade.toFixed(2)}', '{(pnlSummary?.worst_trade ?? 0).toFixed(2)}'),
  @('news && news.length', 'Array.isArray(news) && news.length'),
  @('decisions && decisions.length', 'Array.isArray(decisions) && decisions.length'),
  @('livePositions.positions', '(livePositions?.positions ?? [])')
)

$n = 0
foreach ($p in $pairs) { if ($c.Contains($p[0])) { $c = $c.Replace($p[0], $p[1]); $n++ } }

if ($c -notmatch 'tradesRaw') {
  $c = $c.Replace('const { data: trades, isLoading: tradesLoading } = useGetActiveTrades({', 'const { data: tradesRaw, isLoading: tradesLoading } = useGetActiveTrades({')
  $old = "  });`r`n`r`n  const { data: agentService }"
  $new = "  });`r`n  const trades = Array.isArray(tradesRaw) ? tradesRaw : [];`r`n`r`n  const { data: agentService }"
  if ($c.Contains($old)) { $c = $c.Replace($old, $new); $n++ }
}

Set-Content $path $c -NoNewline
Write-Host "OK v2 - $n fixes. Edge -> http://localhost:5173 then F5" -ForegroundColor Green
