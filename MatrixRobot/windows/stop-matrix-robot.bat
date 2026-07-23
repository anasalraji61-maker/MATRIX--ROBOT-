@echo off
setlocal
echo Stopping Matrix Robot background services...

for /f "tokens=5" %%P in ('netstat -ano ^| findstr ":8080" ^| findstr LISTENING') do taskkill /PID %%P /F >nul 2>&1
for /f "tokens=5" %%P in ('netstat -ano ^| findstr ":5173" ^| findstr LISTENING') do taskkill /PID %%P /F >nul 2>&1

REM Stop Cloudflare phone tunnel (and any leftover project processes)
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$pidFile = Join-Path $env:TEMP 'matrix-robot-tunnel.pid'; if (Test-Path $pidFile) { $p = Get-Content -LiteralPath $pidFile -ErrorAction SilentlyContinue; if ($p) { Stop-Process -Id ([int]$p) -Force -ErrorAction SilentlyContinue }; Remove-Item -Force $pidFile -ErrorAction SilentlyContinue }; Get-CimInstance Win32_Process | Where-Object { ($_.Name -match 'cloudflared' -and $_.CommandLine -match '127\.0\.0\.1:5173|localhost:5173') -or ($_.CommandLine -match 'MatrixRobot|@workspace/dashboard|dist\\\\index\\.mjs') } | ForEach-Object { try { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue } catch {} }; Remove-Item -Force (Join-Path $env:TEMP 'matrix-robot-public-url.txt') -ErrorAction SilentlyContinue" >nul 2>&1

echo Done.
timeout /t 2 >nul
endlocal
