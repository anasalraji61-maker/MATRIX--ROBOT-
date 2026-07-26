# V11 trade review — يحدّث V11_TRADE_REVIEW_REPORT.md (وأرشيف اختياري كل ساعة)
param(
    [switch]$ArchiveHourly,
    [int]$KeepArchiveDays = 7
)

$PyRoot = "C:\MatrixRobot\MatrixRobot\MatrixRobot\artifacts\python-agents"
Set-Location $PyRoot
$env:PYTHONPATH = "."

if (-not (Test-Path ".venv\Scripts\python.exe")) {
    Write-Host "ERROR: .venv not found — run START_BRAIN.bat once first" -ForegroundColor Red
    exit 1
}

$out = Join-Path $PyRoot "V11_TRADE_REVIEW_REPORT.md"
$logDir = Join-Path $PyRoot "reports\scheduler"
New-Item -ItemType Directory -Force -Path $logDir | Out-Null

$stamp = Get-Date -Format "yyyy-MM-dd_HH-mm"
$logFile = Join-Path $logDir "generate_$stamp.log"

try {
    & .\.venv\Scripts\python.exe -m tools.v11_trade_review_report -o $out 2>&1 | Tee-Object -FilePath $logFile
} catch {
    "FAILED: $_" | Out-File -FilePath $logFile -Append
    exit 1
}

if ($LASTEXITCODE -ne 0) {
    Write-Host "Report generation FAILED — see $logFile" -ForegroundColor Red
    exit 1
}

Write-Host "OK: $out ($(Get-Date -Format 'yyyy-MM-dd HH:mm'))" -ForegroundColor Green

if ($ArchiveHourly) {
    $archiveDir = Join-Path $PyRoot "reports\hourly"
    New-Item -ItemType Directory -Force -Path $archiveDir | Out-Null
    $archiveName = "V11_REPORT_$(Get-Date -Format 'yyyy-MM-dd_HH')00.md"
    Copy-Item -Force $out (Join-Path $archiveDir $archiveName)
    Write-Host "Archive: reports\hourly\$archiveName" -ForegroundColor DarkGray

    $cutoff = (Get-Date).AddDays(-$KeepArchiveDays)
    Get-ChildItem $archiveDir -Filter "V11_REPORT_*.md" -ErrorAction SilentlyContinue |
        Where-Object { $_.LastWriteTime -lt $cutoff } |
        Remove-Item -Force -ErrorAction SilentlyContinue
}

exit 0
