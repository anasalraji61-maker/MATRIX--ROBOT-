# نسخ التحديثات إلى VPS — شغّله من جهازك بعد RDP أو انسخ يدوياً
# الملفات المطلوبة على VPS:

$files = @(
    "artifacts\python-agents\tools\account_state.py",
    "artifacts\python-agents\tools\position_reconciler.py",
    "artifacts\python-agents\tools\trade_tiers.py",
    "artifacts\python-agents\tools\prop_rules.py",
    "artifacts\python-agents\agents\data_agent.py",
    "artifacts\python-agents\agents\risk_agent.py",
    "artifacts\python-agents\agents\execution_agent.py",
    "artifacts\python-agents\routes\reconcile.py",
    "artifacts\python-agents\config.py",
    "artifacts\python-agents\main.py",
    "artifacts\api-server\src\routes\agents.ts"
)

Write-Host "Copy these files to VPS (same paths under MatrixRobot):" -ForegroundColor Cyan
$files | ForEach-Object { Write-Host "  $_" }

Write-Host "`nThen on VPS .env add (optional — defaults already ON):" -ForegroundColor Yellow
Write-Host "ENABLE_SMALL_TRADES=true"
Write-Host "POSITION_RECONCILE_INTERVAL_SECONDS=10"

Write-Host "`nRestart:" -ForegroundColor Green
Write-Host "  1. Brain (uvicorn) — REQUIRED"
Write-Host "  2. API (node) — if agents.ts changed"
Write-Host "  Bridge / MT5 — keep running"

Write-Host "`nVerify:" -ForegroundColor Green
Write-Host "  http://127.0.0.1:8080/api/agents/positions/reconcile/status"
Write-Host "  http://127.0.0.1:8080/api/agents/cycle/status"
