@echo off
setlocal
set "HERE=%~dp0"
set "TARGET=%HERE%start-forexvps-hidden.vbs"
set "DESKTOP=%USERPROFILE%\Desktop"
set "SHORTCUT=%DESKTOP%\Matrix Robot VPS.lnk"

powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$ws = New-Object -ComObject WScript.Shell;" ^
  "$s = $ws.CreateShortcut('%SHORTCUT%');" ^
  "$s.TargetPath = '%TARGET%';" ^
  "$s.WorkingDirectory = '%HERE%';" ^
  "$s.WindowStyle = 7;" ^
  "$s.Description = 'Start Matrix Robot permanently on ForexVPS';" ^
  "$s.Save()"

echo Desktop shortcut ready: %SHORTCUT%
pause
endlocal
