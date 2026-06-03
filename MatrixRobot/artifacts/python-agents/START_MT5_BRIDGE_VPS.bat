@echo off
setlocal
title MT5 Bridge (VPS direct)
cd /d "%~dp0"

echo ==========================================
echo   MT5 Bridge - VPS (direct, no tunnel)
echo ==========================================
echo.
echo Bridge binds 0.0.0.0:5555 - reachable via VPS public IP.
echo.
echo Make sure:
echo   1. Windows Firewall allows inbound TCP 5555
echo   2. .env contains MT5_LOGIN/PASSWORD/SERVER + BRIDGE_SECRET
echo   3. MT5 Desktop is installed and logged in
echo.

python mt5_windows_bridge.py

echo.
echo Bridge stopped. Press any key to exit.
pause >nul
