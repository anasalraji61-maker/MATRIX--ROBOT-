@echo off
title Matrix Robot - Master Launcher
color 0E
cd /d "%~dp0"

echo ============================================
echo   Matrix Robot - Auto Launcher
echo ============================================
echo.
echo Opening MT5 Bridge and Cloudflare Tunnel...
echo (this window will close in 15 seconds)
echo.

REM ── 1) Bridge ──
start "MT5 Bridge - DO NOT CLOSE" cmd /k "%~dp0START_MT5_BRIDGE.bat"

REM Wait for bridge to bind before starting tunnel
timeout /t 10 /nobreak >nul

REM ── 2) Cloudflare Tunnel ──
if exist "%~dp0cloudflared.exe" (
    start "Cloudflare Tunnel - DO NOT CLOSE" cmd /k ""%~dp0cloudflared.exe" tunnel --url http://localhost:5555"
) else (
    echo.
    echo ERROR: cloudflared.exe not found in this folder.
    echo Download from: https://github.com/cloudflare/cloudflared/releases/latest
    echo File: cloudflared-windows-amd64.exe  -^>  rename to cloudflared.exe
    timeout /t 30 /nobreak >nul
    exit /b 1
)

echo Done. The 2 new windows must stay open.
echo Remember to copy the new trycloudflare.com URL into Replit Secrets.
timeout /t 15 /nobreak >nul
exit /b 0
