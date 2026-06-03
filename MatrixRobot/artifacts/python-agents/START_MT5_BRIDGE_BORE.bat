@echo off
setlocal enabledelayedexpansion
title MT5 Bridge (bore.pub tunnel)
cd /d "%~dp0"

echo ==========================================
echo   MT5 Bridge - bore.pub tunnel
echo ==========================================
echo.

REM --- Download bore.exe if missing ---
if not exist "bore.exe" (
    echo [1/3] Downloading bore.exe ^(~3MB^)...
    curl -L -o bore.zip "https://github.com/ekzhang/bore/releases/download/v0.5.3/bore-v0.5.3-x86_64-pc-windows-msvc.zip"
    if errorlevel 1 (
        echo ERROR: Failed to download bore.exe
        echo Download manually from: https://github.com/ekzhang/bore/releases
        pause
        exit /b 1
    )
    powershell -Command "Expand-Archive -Path bore.zip -DestinationPath . -Force"
    del bore.zip
    if not exist "bore.exe" (
        echo ERROR: bore.exe extraction failed
        pause
        exit /b 1
    )
    echo bore.exe ready.
    echo.
)

REM --- Start MT5 bridge in a new window ---
echo [2/3] Starting MT5 bridge on port 5555...
start "MT5 Bridge (port 5555)" cmd /k "cd /d ""%~dp0"" && python mt5_windows_bridge.py"
timeout /t 5 /nobreak >nul

REM --- Start bore tunnel ---
echo [3/3] Starting bore.pub tunnel...
echo.
echo ==========================================
echo   WATCH FOR A LINE LIKE:
echo     listening at bore.pub:XXXXX
echo   Send the URL to Replit:
echo     http://bore.pub:XXXXX
echo ==========================================
echo.

bore.exe local 5555 --to bore.pub

echo.
echo Tunnel closed. Press any key to exit.
pause >nul
