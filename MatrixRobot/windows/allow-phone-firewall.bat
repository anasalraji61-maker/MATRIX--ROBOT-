@echo off
REM Optional: LAN-only access on the same Wi-Fi (port 5173).
REM Phone access over Asia cell / internet does NOT need this —
REM the desktop launcher already opens a public Cloudflare HTTPS tunnel.
netsh advfirewall firewall delete rule name="MatrixRobot Dashboard 5173" >nul 2>&1
netsh advfirewall firewall add rule name="MatrixRobot Dashboard 5173" dir=in action=allow protocol=TCP localport=5173
echo Firewall rule added for port 5173 (LAN optional).
echo For cellular / any network: use the public HTTPS URL from the Matrix Robot popup.
pause
