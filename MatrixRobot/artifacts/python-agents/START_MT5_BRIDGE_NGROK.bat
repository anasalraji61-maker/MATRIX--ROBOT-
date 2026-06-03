@echo off
setlocal enabledelayedexpansion
title Matrix Robot - MT5 Bridge (ngrok)
color 0B

echo ============================================
echo   Matrix Robot - MT5 Windows Bridge (ngrok)
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

echo ERROR: Python not found. Install from https://www.python.org/downloads/
pause
exit /b 1

:PYTHON_FOUND
echo [OK] Python found: %PYTHON_EXE%
echo.

REM ====================================================
REM  STEP 2: Install bridge deps
REM ====================================================
echo Installing bridge dependencies (first run only)...
%PYTHON_EXE% -m pip install --quiet --disable-pip-version-check MetaTrader5 fastapi uvicorn python-dotenv
if errorlevel 1 (
    echo ERROR: Failed to install dependencies.
    pause
    exit /b 1
)
echo [OK] Dependencies installed.
echo.

REM ====================================================
REM  STEP 3: Ensure ngrok.exe exists
REM ====================================================
cd /d "%~dp0"
if not exist "ngrok.exe" (
    echo Downloading ngrok ^(~15 MB, one time only^)...
    powershell -Command "Invoke-WebRequest -Uri 'https://bin.equinox.io/c/bNyj1mQVY4c/ngrok-v3-stable-windows-amd64.zip' -OutFile 'ngrok.zip'"
    if errorlevel 1 (
        echo ERROR: Failed to download ngrok.
        pause
        exit /b 1
    )
    powershell -Command "Expand-Archive -Path 'ngrok.zip' -DestinationPath '.' -Force"
    del ngrok.zip
    echo [OK] ngrok downloaded.
    echo.
)

REM ====================================================
REM  STEP 4: Configure ngrok authtoken (first run only)
REM ====================================================
if not exist "ngrok_authtoken.txt" (
    echo.
    echo ============================================
    echo   FIRST-TIME SETUP - ngrok authtoken needed
    echo ============================================
    echo.
    echo 1. Sign up free at:  https://dashboard.ngrok.com/signup
    echo 2. Copy your authtoken from:
    echo    https://dashboard.ngrok.com/get-started/your-authtoken
    echo 3. Paste it below and press Enter.
    echo.
    set /p NGROK_TOKEN="Authtoken: "
    echo !NGROK_TOKEN!> ngrok_authtoken.txt
    ngrok.exe config add-authtoken !NGROK_TOKEN!
    if errorlevel 1 (
        del ngrok_authtoken.txt
        echo ERROR: Invalid authtoken.
        pause
        exit /b 1
    )
    echo [OK] Authtoken saved.
    echo.
)

REM ====================================================
REM  STEP 5: Start MT5 bridge in background window
REM ====================================================
echo Starting MT5 bridge on port 5555...
start "MT5 Bridge (port 5555)" /MIN %PYTHON_EXE% mt5_windows_bridge.py

timeout /t 5 /nobreak >nul

REM ====================================================
REM  STEP 6: Start ngrok tunnel
REM ====================================================
echo.
echo ============================================
echo   Starting ngrok tunnel...
echo   PUBLIC URL will appear below in a moment.
echo   Look for: https://xxxxx.ngrok-free.app
echo ============================================
echo.
echo *** DO NOT CLOSE THIS WINDOW ***
echo.

ngrok.exe http 5555 --log=stdout

echo.
echo Tunnel stopped. Press any key to close...
pause >nul
