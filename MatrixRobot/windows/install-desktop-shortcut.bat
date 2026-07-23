@echo off
setlocal
set "ROOT=%~dp0"
set "TARGET=%ROOT%start-matrix-robot-hidden.vbs"
set "DESKTOP=%USERPROFILE%\Desktop"
set "SHORTCUT=%DESKTOP%\Matrix Robot.lnk"

powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$s = (New-Object -ComObject WScript.Shell).CreateShortcut('%SHORTCUT%');" ^
  "$s.TargetPath = '%TARGET%';" ^
  "$s.WorkingDirectory = '%ROOT%';" ^
  "$s.WindowStyle = 7;" ^
  "$s.Description = 'Start Matrix Robot locally';" ^
  "$s.Save()"

echo Desktop shortcut created:
echo   %SHORTCUT%
echo.
echo Double-click "Matrix Robot" on the Desktop to start.
pause
endlocal
