@echo off
REM Allow phone access to Dashboard on the same Wi-Fi (port 5173)
netsh advfirewall firewall delete rule name="MatrixRobot Dashboard 5173" >nul 2>&1
netsh advfirewall firewall add rule name="MatrixRobot Dashboard 5173" dir=in action=allow protocol=TCP localport=5173
echo Firewall rule added for port 5173.
pause
