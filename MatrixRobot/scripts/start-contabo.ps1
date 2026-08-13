# Matrix Robot — تشغيل يدوي على Contabo Windows (للاختبار قبل الخدمات التلقائية)
$ErrorActionPreference = "Stop"
$Root = if ($env:MATRIX_ROOT) { $env:MATRIX_ROOT } else { "C:\MatrixRobot\MatrixRobot" }

if (-not (Test-Path "$Root\.env")) {
  Write-Host "أنشئ $Root\.env من .env.example أولاً" -ForegroundColor Red
  exit 1
}

# تحميل .env بسيط (KEY=VALUE)
Get-Content "$Root\.env" | ForEach-Object {
  if ($_ -match '^\s*([^#][^=]+)=(.*)$') {
    [System.Environment]::SetEnvironmentVariable($matches[1].Trim(), $matches[2].Trim().Trim('"'), "Process")
  }
}

$py = "$Root\artifacts\python-agents\.venv\Scripts\python.exe"
$apiDir = "$Root\artifacts\api-server"

if (-not (Test-Path $py)) {
  Write-Host "نفّذ: cd $Root\artifacts\python-agents && py -m venv .venv && pip install -r requirements.txt"
  exit 1
}

Write-Host "Starting Python :8000 ..."
Start-Process -FilePath $py -ArgumentList "-m","uvicorn","main:app","--host","127.0.0.1","--port","8000" `
  -WorkingDirectory "$Root\artifacts\python-agents" -WindowStyle Minimized

Start-Sleep -Seconds 3

if (-not $env:PORT) { $env:PORT = "8080" }
if (-not $env:PYTHON_AGENT_URL) { $env:PYTHON_AGENT_URL = "http://127.0.0.1:8000" }

Write-Host "Starting API :$($env:PORT) ..."
Start-Process -FilePath "node" -ArgumentList "--enable-source-maps","./dist/index.mjs" `
  -WorkingDirectory $apiDir -WindowStyle Minimized

Write-Host "OK — Python 8000 + API $($env:PORT). شغّل MT5 Bridge منفصلاً. للداشبورد: pnpm --filter @workspace/dashboard run build ثم preview أو Tunnel."
