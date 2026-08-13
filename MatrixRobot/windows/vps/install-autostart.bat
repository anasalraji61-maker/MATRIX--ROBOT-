@echo off
setlocal EnableExtensions
set "HERE=%~dp0"
set "STARTBAT=%HERE%start-forexvps.bat"
set "TASK=MatrixRobot ForexVPS"

echo.
echo Creating Windows Task Scheduler entry:
echo   Name: %TASK%
echo   Trigger: at user logon
echo   Action: %STARTBAT%
echo.

schtasks /Create /TN "%TASK%" /TR "\"%STARTBAT%\"" /SC ONLOGON /RL LIMITED /F
if errorlevel 1 (
  echo Failed to create scheduled task. Run this bat as Administrator and retry.
  pause
  exit /b 1
)

echo.
echo Autostart enabled. After RDP login / reboot+login, Matrix Robot will start.
echo To remove later:
echo   schtasks /Delete /TN "%TASK%" /F
echo.
pause
endlocal
exit /b 0
