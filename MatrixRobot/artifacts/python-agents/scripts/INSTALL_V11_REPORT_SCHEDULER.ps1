# جدولة تقرير V11 — كل ساعة (تكلفة شبه صفر: قراءة DB فقط، بدون GPT)
# شغّل PowerShell كـ Administrator مرة واحدة على الـ VPS

$TaskName = "MatrixV11HourlyTradeReport"
$ScriptPath = "C:\MatrixRobot\MatrixRobot\MatrixRobot\artifacts\python-agents\scripts\GENERATE_V11_TRADE_REVIEW.ps1"

if (-not (Test-Path $ScriptPath)) {
    Write-Host "ERROR: Script not found: $ScriptPath" -ForegroundColor Red
    exit 1
}

$tr = "powershell.exe -NoProfile -ExecutionPolicy Bypass -File `"$ScriptPath`" -ArchiveHourly"

# إزالة مهمة قديمة إن وُجدت
schtasks /Delete /TN $TaskName /F 2>$null | Out-Null

# كل ساعة — يبدأ بعد دقيقة من التثبيت
schtasks /Create /TN $TaskName /TR $tr /SC HOURLY /MO 1 /F | Out-Null

if ($LASTEXITCODE -eq 0) {
    Write-Host "OK: Scheduled task '$TaskName' — runs every hour" -ForegroundColor Green
    Write-Host "Latest report: ...\python-agents\V11_TRADE_REVIEW_REPORT.md" -ForegroundColor Cyan
    Write-Host "Hourly copies:  ...\python-agents\reports\hourly\" -ForegroundColor Cyan
    Write-Host ""
    Write-Host "Test now:" -ForegroundColor Yellow
    Write-Host "  powershell -File `"$ScriptPath`" -ArchiveHourly"
    Write-Host ""
    Write-Host "Remove scheduler:" -ForegroundColor DarkGray
    Write-Host "  schtasks /Delete /TN $TaskName /F"
} else {
    Write-Host "FAILED to create task — try Run as Administrator" -ForegroundColor Red
    exit 1
}
