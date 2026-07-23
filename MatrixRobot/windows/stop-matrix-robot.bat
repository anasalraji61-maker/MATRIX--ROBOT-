@echo off
setlocal
echo Stopping Matrix Robot background services...

for /f "tokens=5" %%P in ('netstat -ano ^| findstr ":8080" ^| findstr LISTENING') do taskkill /PID %%P /F >nul 2>&1
for /f "tokens=5" %%P in ('netstat -ano ^| findstr ":5173" ^| findstr LISTENING') do taskkill /PID %%P /F >nul 2>&1

REM Also stop leftover pnpm/vite/node started for this project (best-effort)
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -match 'MatrixRobot|@workspace/dashboard|dist\\\\index\\.mjs' } | ForEach-Object { try { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue } catch {} }" >nul 2>&1

echo Done.
timeout /t 2 >nul
endlocal
