@echo off
title Matrix Robot - MT5 Bridge
color 0A

echo ============================================
echo   Matrix Robot - MT5 Windows Bridge
echo ============================================
echo.

REM ====================================================
REM  STEP 1: Find / install Python
REM ====================================================
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

echo Python not found. Installing automatically via winget...
echo.
winget --version >nul 2>&1
if errorlevel 1 (
    echo ERROR: winget not available.
    echo Please install Python manually from https://www.python.org/downloads/
    echo Make sure to tick "Add Python to PATH".
    pause
    exit /b 1
)
winget install --id Python.Python.3.11 --silent --accept-package-agreements --accept-source-agreements
echo.
echo Python installed. Close this window and double-click START_MT5_BRIDGE.bat AGAIN.
pause
exit /b 0

:PYTHON_FOUND
echo [OK] Python found: %PYTHON_EXE%
%PYTHON_EXE% --version
echo.

REM ====================================================
REM  STEP 2: Install bridge deps
REM ====================================================
echo Installing bridge dependencies (first run only)...
%PYTHON_EXE% -m pip install --quiet --disable-pip-version-check MetaTrader5 fastapi uvicorn python-dotenv
if errorlevel 1 (
    echo ERROR: Failed to install dependencies. Check internet.
    pause
    exit /b 1
)
echo [OK] Dependencies installed.
echo.

REM ====================================================
REM  STEP 3: Ensure cloudflared.exe exists (for public URL)
REM ====================================================
cd /d "%~dp0"
if not exist "cloudflared.exe" (
    echo Downloading cloudflared.exe ^(~20 MB, one time only^)...
    powershell -Command "Invoke-WebRequest -Uri 'https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-windows-amd64.exe' -OutFile 'cloudflared.exe'"
    if errorlevel 1 (
        echo ERROR: Failed to download cloudflared. Check internet.
        pause
        exit /b 1
    )
    echo [OK] cloudflared downloaded.
    echo.
)

REM ====================================================
REM  STEP 4: Start the MT5 bridge in background window
REM ====================================================
echo Starting MT5 bridge on port 5555...
start "MT5 Bridge (port 5555)" /MIN %PYTHON_EXE% mt5_windows_bridge.py

REM Give it a few seconds to boot
timeout /t 5 /nobreak >nul

REM ====================================================
REM  STEP 5: Start cloudflared tunnel
REM ====================================================
echo.
echo ============================================
echo   Starting Cloudflare tunnel...
echo   PUBLIC URL will appear below in a moment.
echo   Look for: https://xxxxx.trycloudflare.com
echo ============================================
echo.
echo *** DO NOT CLOSE THIS WINDOW ***
echo *** DO NOT PRESS Ctrl+C ***
echo.

cloudflared.exe tunnel --no-autoupdate --url http://127.0.0.1:5555

echo.
echo Tunnel stopped. Press any key to close...
pause >nul
