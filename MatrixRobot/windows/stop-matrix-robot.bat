@echo off
echo Stopping Matrix Robot local services...

REM Stop node processes started for API / Vite dashboard (best-effort)
for /f "tokens=5" %%P in ('netstat -ano ^| findstr ":8080" ^| findstr LISTENING') do taskkill /PID %%P /F >nul 2>&1
for /f "tokens=5" %%P in ('netstat -ano ^| findstr ":5173" ^| findstr LISTENING') do taskkill /PID %%P /F >nul 2>&1

echo Done.
timeout /t 2 /nobreak >nul
