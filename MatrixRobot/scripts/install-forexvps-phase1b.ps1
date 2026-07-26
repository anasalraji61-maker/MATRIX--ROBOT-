# Matrix Robot — ForexVPS Phase 1b (بعد إعادة فتح PowerShell)
# غيّر $RepoUrl إلى رابط GitHub الخاص بك (نفس Contabo)
$ErrorActionPreference = "Stop"
$Root = "C:\MatrixRobot"
$RepoUrl = "PUT_YOUR_GITHUB_REPO_URL_HERE"

if ($RepoUrl -eq "PUT_YOUR_GITHUB_REPO_URL_HERE") {
  Write-Host "عدّل RepoUrl في هذا الملف أو استنسخ المجلد يدوياً إلى C:\MatrixRobot" -ForegroundColor Red
  exit 1
}

if (-not (Test-Path $Root)) {
  git clone $RepoUrl $Root
}

Set-Location $Root
pnpm install --ignore-scripts

Set-Location "$Root\artifacts\python-agents"
python -m venv .venv
.\.venv\Scripts\pip install -r requirements.txt
.\.venv\Scripts\pip install MetaTrader5

Set-Location "$Root\artifacts\api-server"
node build.mjs

Set-Location "$Root\artifacts\dashboard"
$env:PORT = "8080"
$env:BASE_PATH = "/"
$env:NODE_ENV = "production"
pnpm run build

Write-Host "OK Phase 1 — انتظر .env من Contabo ثم Phase 2" -ForegroundColor Green
