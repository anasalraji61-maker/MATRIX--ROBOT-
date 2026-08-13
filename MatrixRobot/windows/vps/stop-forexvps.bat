@echo off
setlocal
echo Stopping Matrix Robot ForexVPS services (API / Brain / phone tunnel)...
echo MT5 terminal is left running.

for /f "tokens=5" %%P in ('netstat -ano ^| findstr ":8080" ^| findstr LISTENING') do taskkill /PID %%P /F >nul 2>&1
for /f "tokens=5" %%P in ('netstat -ano ^| findstr ":8000" ^| findstr LISTENING') do taskkill /PID %%P /F >nul 2>&1

powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$pidFile = Join-Path $env:TEMP 'matrix-robot-vps-tunnel.pid'; if (Test-Path $pidFile) { $p = Get-Content -LiteralPath $pidFile -ErrorAction SilentlyContinue; if ($p) { Stop-Process -Id ([int]$p) -Force -ErrorAction SilentlyContinue }; Remove-Item -Force $pidFile -ErrorAction SilentlyContinue }; Get-CimInstance Win32_Process | Where-Object { ($_.Name -match 'cloudflared' -and $_.CommandLine -match '127\.0\.0\.1:8080|localhost:8080') -or ($_.CommandLine -match 'uvicorn.*main:app|artifacts\\\\api-server\\\\dist\\\\index\\.mjs') } | ForEach-Object { try { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue } catch {} }; Remove-Item -Force (Join-Path $env:TEMP 'matrix-robot-vps-public-url.txt') -ErrorAction SilentlyContinue" >nul 2>&1

echo Done.
timeout /t 2 >nul
endlocal
