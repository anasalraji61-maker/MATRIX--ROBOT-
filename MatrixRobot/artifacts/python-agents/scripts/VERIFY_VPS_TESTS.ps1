# VPS verify - install test deps and run full pytest (ASCII only)
# Run from: artifacts\python-agents
#   powershell -ExecutionPolicy Bypass -File scripts\VERIFY_VPS_TESTS.ps1

$ErrorActionPreference = "Stop"
$PyRoot = $PSScriptRoot
if ($PyRoot -match "scripts$") {
    $PyRoot = Split-Path $PyRoot -Parent
}
Set-Location $PyRoot
$env:PYTHONPATH = "."

if (-not (Test-Path ".venv\Scripts\python.exe")) {
    Write-Host "ERROR: .venv missing - run START_BRAIN.bat once first" -ForegroundColor Red
    exit 1
}

$Python = ".venv\Scripts\python.exe"

Write-Host "=== Matrix Robot VPS Verify ===" -ForegroundColor Cyan
Write-Host "Installing pytest-asyncio + requirements..."
& $Python -m pip install --upgrade pip --quiet
& $Python -m pip install -r requirements.txt --quiet
& $Python -m pip install pytest-asyncio --quiet

Write-Host "compileall..."
& $Python -m compileall -q .
if ($LASTEXITCODE -ne 0) { exit 1 }

Write-Host "pytest..."
& $Python -m pytest -q --tb=line
if ($LASTEXITCODE -ne 0) {
    Write-Host "FAIL" -ForegroundColor Red
    exit 1
}

Write-Host "OK: all tests passed" -ForegroundColor Green
Write-Host "Health: http://127.0.0.1:8000/agents/health"
