@echo off
title Matrix Robot - MT5 Bridge (ForexIraq, port 5556)
color 0B

echo ============================================
echo   Matrix Robot - ForexIraq Bridge
echo   Port: 5556
echo ============================================
echo.

REM ============================================
REM   STEP 1: Edit these 3 lines with your
REM   ForexIraq MT5 credentials, then save.
REM ============================================
set "MT5_LOGIN=PUT_YOUR_FOREXIRAQ_LOGIN_HERE"
set "MT5_PASSWORD=PUT_YOUR_FOREXIRAQ_PASSWORD_HERE"
set "MT5_SERVER=PUT_YOUR_FOREXIRAQ_SERVER_HERE"

REM Port for this 2nd bridge (must NOT clash with FundedNext bridge on 5555)
set "BRIDGE_PORT=5556"

REM ── Find Python executable ──
set "PYTHON_EXE="
python --version >nul 2>&1
if not errorlevel 1 (
    set "PYTHON_EXE=python"
    goto :PYTHON_FOUND
)
py --version >nul 2>&1
if not errorlevel 1 (
    set "PYTHON_EXE=py"
    goto :PYTHON_FOUND
)
for %%P in (
    "%LOCALAPPDATA%\Programs\Python\Python312\python.exe"
    "%LOCALAPPDATA%\Programs\Python\Python311\python.exe"
    "%LOCALAPPDATA%\Programs\Python\Python310\python.exe"
    "C:\Program Files\Python312\python.exe"
    "C:\Program Files\Python311\python.exe"
    "C:\Python311\python.exe"
) do (
    if exist "%%~P" (
        set "PYTHON_EXE=%%~P"
        goto :PYTHON_FOUND
    )
)

echo ERROR: Python not found.
echo Install Python first (or run START_MT5_BRIDGE.bat once - it auto-installs).
pause
exit /b 1

:PYTHON_FOUND
echo Python found: %PYTHON_EXE%
%PYTHON_EXE% --version
echo.

REM ── Install dependencies (safe to re-run) ──
echo Installing bridge dependencies...
%PYTHON_EXE% -m pip install --quiet --disable-pip-version-check MetaTrader5 fastapi uvicorn python-dotenv

REM ── Sanity check: credentials filled in ──
if "%MT5_LOGIN%"=="PUT_YOUR_FOREXIRAQ_LOGIN_HERE" (
    echo.
    echo ERROR: Open this .bat file in Notepad and fill in your
    echo        ForexIraq login, password, and server name first.
    echo.
    pause
    exit /b 1
)

echo.
echo ============================================
echo   Starting ForexIraq Bridge on port %BRIDGE_PORT%
echo   Login : %MT5_LOGIN%
echo   Server: %MT5_SERVER%
echo   Keep this window open while trading.
echo ============================================
echo.

REM ── Run bridge from script directory ──
cd /d "%~dp0"
%PYTHON_EXE% mt5_windows_bridge.py

pause
