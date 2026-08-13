# V11 surgical hotfix — extract zip + copy files to correct folders (VPS)
param(
    [string]$ZipPath = "C:\Users\Administrator\Downloads\v11_surgical_hotfix.zip"
)

$root = "C:\MatrixRobot\MatrixRobot\MatrixRobot\artifacts\python-agents"
if (-not (Test-Path $ZipPath)) {
    Write-Host "ZIP not found: $ZipPath" -ForegroundColor Red
    Write-Host "Search: Get-ChildItem C:\Users -Recurse -Filter v11_surgical_hotfix.zip"
    exit 1
}

Write-Host "Extracting $ZipPath -> $root" -ForegroundColor Cyan
Expand-Archive -Path $ZipPath -DestinationPath $root -Force

$toTools = @(
    "surgical_filters.py", "data_quality.py", "account_state.py", "risk_sizing.py",
    "scalp_risk.py", "scalp_engine.py", "close_logger.py", "ml_filter.py",
    "position_manager.py", "risk_batch.py", "v11_trade_review_report.py"
)
$toAgents = @("execution_agent.py")
$toScripts = @("GENERATE_V11_TRADE_REVIEW.ps1", "INSTALL_V11_REPORT_SCHEDULER.ps1")

New-Item -ItemType Directory -Force -Path (Join-Path $root "tools") | Out-Null
New-Item -ItemType Directory -Force -Path (Join-Path $root "agents") | Out-Null
New-Item -ItemType Directory -Force -Path (Join-Path $root "scripts") | Out-Null

function Copy-Into($name, $sub) {
    $src = Join-Path $root $name
    $dst = Join-Path $root $sub $name
    if (Test-Path $src) {
        Copy-Item -Force $src $dst
        Write-Host "OK $sub\$name" -ForegroundColor Green
        return $true
    }
    return $false
}

foreach ($f in $toTools) { Copy-Into $f "tools" | Out-Null }
foreach ($f in $toAgents) { Copy-Into $f "agents" | Out-Null }
foreach ($f in $toScripts) { Copy-Into $f "scripts" | Out-Null }

# config.py stays in root (overwrite)
if (Test-Path (Join-Path $root "config.py")) {
    Write-Host "OK config.py (root)" -ForegroundColor Green
}

$ok = Test-Path (Join-Path $root "tools\surgical_filters.py")
if ($ok) {
    Write-Host "`nDONE — restart Brain: .\START_BRAIN.bat" -ForegroundColor Green
} else {
    Write-Host "`nFAILED — tools\surgical_filters.py missing" -ForegroundColor Red
    exit 1
}
