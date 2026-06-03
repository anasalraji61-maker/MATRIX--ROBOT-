@echo off
title Matrix Robot - BRAIN (AI Agents) - DO NOT CLOSE
color 0A
cd /d "%~dp0"

echo ============================================
echo   Matrix Robot - BRAIN (AI Agents)
echo ============================================
echo.

REM ---- 1) Find Python (3.11+) ----
set "PY="
where py >nul 2>&1 && set "PY=py -3"
if not defined PY (
  where python >nul 2>&1 && set "PY=python"
)
if not defined PY (
  echo ERROR: Python not found. Install Python 3.11+ from https://www.python.org/downloads/
  echo Make sure to check "Add Python to PATH" during install.
  pause
  exit /b 1
)

echo Using Python: %PY%
%PY% --version
echo.

REM ---- 2) Create virtual environment (first run only) ----
if not exist ".venv\Scripts\python.exe" (
  echo [setup] Creating virtual environment...
  %PY% -m venv .venv
)

REM ---- 3) Install dependencies ----
echo [setup] Installing dependencies (first run can take a few minutes)...
".venv\Scripts\python.exe" -m pip install --upgrade pip --quiet
".venv\Scripts\python.exe" -m pip install -r requirements.txt --quiet
echo [setup] Dependencies ready.
echo.

REM ---- 4) Start the brain on port 8000 ----
echo [run] Starting Matrix Robot brain on port 8000...
echo [run] Keep this window OPEN. Close it = robot stops.
echo.
set PORT=8000
".venv\Scripts\python.exe" -m uvicorn main:app --host 0.0.0.0 --port 8000 --log-level info

echo.
echo Brain stopped. Press any key to close.
pause >nul
