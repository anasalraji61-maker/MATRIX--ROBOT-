@echo off
title Matrix Robot - Backtest EURUSD
color 0B
cd /d "%~dp0"

echo ============================================
echo   Backtest EURUSD H1 (2000 bars)
echo ============================================
echo.

if not exist ".venv\Scripts\python.exe" (
  echo ERROR: Run START_BRAIN.bat once first to create .venv
  pause
  exit /b 1
)

".venv\Scripts\python.exe" scripts\run_backtest_one.py EURUSD

echo.
pause
