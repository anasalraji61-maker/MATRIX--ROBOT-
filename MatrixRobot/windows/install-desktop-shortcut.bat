@echo off
setlocal
set "HERE=%~dp0"
set "TARGET=%HERE%start-matrix-robot-hidden.vbs"
set "DESKTOP=%USERPROFILE%\Desktop"
set "SHORTCUT=%DESKTOP%\Matrix Robot.lnk"

powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$ws = New-Object -ComObject WScript.Shell;" ^
  "$s = $ws.CreateShortcut('%SHORTCUT%');" ^
  "$s.TargetPath = '%TARGET%';" ^
  "$s.WorkingDirectory = '%HERE%';" ^
  "$s.WindowStyle = 7;" ^
  "$s.Description = 'Start Matrix Robot in background';" ^
  "$s.Save()"

echo.
echo Desktop shortcut ready:
echo   %SHORTCUT%
echo.
echo Usage:
echo   1) Double-click "Matrix Robot" on Desktop
echo   2) Wait for the popup — it includes a public HTTPS phone link
echo   3) On iPhone (Asia cell / any network), open that link in Safari
echo   4) Share -^> Add to Home Screen
echo.
echo Note: the public link changes each time you start (trycloudflare.com).
echo       Laptop must stay on and Matrix Robot running for phone access.
echo.
pause
endlocal
