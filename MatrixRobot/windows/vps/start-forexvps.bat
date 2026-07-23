@echo off
setlocal EnableExtensions
cd /d "%~dp0..\.."
set "ROOT=%CD%"
set "LOG=%TEMP%\matrix-robot-vps-start.log"
set "URLFILE=%TEMP%\matrix-robot-vps-public-url.txt"
set "PUBLICURL="

echo ===== ForexVPS start %DATE% %TIME% =====> "%LOG%"
echo ROOT=%ROOT%>> "%LOG%"

set "PATH=%ProgramFiles%\nodejs;%ProgramFiles(x86)%\nodejs;%APPDATA%\npm;%LOCALAPPDATA%\pnpm;%USERPROFILE%\.local\bin;%PATH%"

if not exist "%ROOT%\.env" (
  powershell -NoProfile -Command "Add-Type -AssemblyName PresentationFramework; [System.Windows.MessageBox]::Show('ملف .env غير موجود على الـ VPS. انسخه من اللابتوب ثم شغّل install-forexvps.bat','Matrix Robot VPS')"
  exit /b 1
)

powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0ensure-vps-env.ps1" -Root "%ROOT%" >> "%LOG%" 2>&1

if exist "lib\api-zod\src\generated\api.ts" (
  powershell -NoProfile -ExecutionPolicy Bypass -Command ^
    "(Get-Content -LiteralPath 'lib\api-zod\src\generated\api.ts' -Raw) -replace 'zod\.looseObject','zod.object' | Set-Content -LiteralPath 'lib\api-zod\src\generated\api.ts' -NoNewline" >> "%LOG%" 2>&1
)

if not exist "artifacts\api-server\dist\index.mjs" (
  echo Building API...>> "%LOG%"
  pushd "artifacts\api-server"
  node ".\build.mjs" >> "%LOG%" 2>&1
  if errorlevel 1 (
    popd
    powershell -NoProfile -Command "Add-Type -AssemblyName PresentationFramework; [System.Windows.MessageBox]::Show('فشل بناء API. شغّل install-forexvps.bat أولاً.','Matrix Robot VPS')"
    exit /b 1
  )
  popd
)

if not exist "artifacts\dashboard\dist\public\index.html" (
  echo Building Dashboard...>> "%LOG%"
  set "PORT=5173"
  set "BASE_PATH=/"
  call pnpm --filter @workspace/dashboard run build >> "%LOG%" 2>&1
  if errorlevel 1 (
    powershell -NoProfile -Command "Add-Type -AssemblyName PresentationFramework; [System.Windows.MessageBox]::Show('فشل بناء الواجهة. شغّل install-forexvps.bat أولاً.','Matrix Robot VPS')"
    exit /b 1
  )
)

REM Free API/brain ports only (do not kill MT5)
for /f "tokens=5" %%P in ('netstat -ano ^| findstr ":8080" ^| findstr LISTENING') do taskkill /PID %%P /F >> "%LOG%" 2>&1
for /f "tokens=5" %%P in ('netstat -ano ^| findstr ":8000" ^| findstr LISTENING') do taskkill /PID %%P /F >> "%LOG%" 2>&1

REM Ensure MT5 bridge on :5555 (start if missing)
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$c=Get-NetTCPConnection -LocalPort 5555 -State Listen -ErrorAction SilentlyContinue; if(-not $c){ Start-Process -WindowStyle Minimized -WorkingDirectory '%ROOT%\artifacts\python-agents' -FilePath 'python' -ArgumentList 'mt5_windows_bridge.py' }" >> "%LOG%" 2>&1

REM Start Brain (FastAPI) hidden
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$py = Join-Path '%ROOT%' 'artifacts\python-agents\.venv\Scripts\python.exe'; if (-not (Test-Path $py)) { $py = 'python' }; Start-Process -WindowStyle Hidden -WorkingDirectory '%ROOT%\artifacts\python-agents' -FilePath $py -ArgumentList '-m','uvicorn','main:app','--host','0.0.0.0','--port','8000','--log-level','info'" >> "%LOG%" 2>&1

REM Wait for brain
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$ok=$false; 1..40 | ForEach-Object { Start-Sleep -Seconds 1; $c=Get-NetTCPConnection -LocalPort 8000 -State Listen -ErrorAction SilentlyContinue; if($c){$ok=$true; break} }; if(-not $ok){ exit 1 }" >> "%LOG%" 2>&1
if errorlevel 1 (
  echo Brain did not start — trying START_BRAIN setup path...>> "%LOG%"
  start "Matrix Brain setup" /MIN cmd /c "cd /d \"%ROOT%\artifacts\python-agents\" && START_BRAIN.bat"
  powershell -NoProfile -ExecutionPolicy Bypass -Command ^
    "$ok=$false; 1..90 | ForEach-Object { Start-Sleep -Seconds 1; $c=Get-NetTCPConnection -LocalPort 8000 -State Listen -ErrorAction SilentlyContinue; if($c){$ok=$true; break} }; if(-not $ok){ exit 1 }" >> "%LOG%" 2>&1
  if errorlevel 1 (
    powershell -NoProfile -Command "Add-Type -AssemblyName PresentationFramework; [System.Windows.MessageBox]::Show('تعذر تشغيل Brain على المنفذ 8000. راجع السجل.','Matrix Robot VPS')"
    exit /b 1
  )
)

REM Start API (serves Dashboard SPA + /api on :8080)
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "Start-Process -WindowStyle Hidden -WorkingDirectory '%ROOT%\artifacts\api-server' -FilePath 'node' -ArgumentList '--env-file=..\..\.env','--enable-source-maps','.\dist\index.mjs'" >> "%LOG%" 2>&1

powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$ok=$false; 1..30 | ForEach-Object { Start-Sleep -Seconds 1; $c=Get-NetTCPConnection -LocalPort 8080 -State Listen -ErrorAction SilentlyContinue; if($c){$ok=$true; break} }; if(-not $ok){ exit 1 }" >> "%LOG%" 2>&1
if errorlevel 1 (
  powershell -NoProfile -Command "Add-Type -AssemblyName PresentationFramework; [System.Windows.MessageBox]::Show('تعذر تشغيل API على 8080. راجع السجل: %LOG%','Matrix Robot VPS')"
  exit /b 1
)

REM Public HTTPS for iPhone (Asia cell / any network)
echo Starting public tunnel...>> "%LOG%"
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0start-public-tunnel.ps1" >> "%LOG%" 2>&1
if exist "%URLFILE%" set /p PUBLICURL=<"%URLFILE%"

start "" "http://127.0.0.1:8080/"

if defined PUBLICURL (
  echo Public URL: %PUBLICURL%>> "%LOG%"
  powershell -NoProfile -ExecutionPolicy Bypass -Command "Add-Type -AssemblyName PresentationFramework; $u = Get-Content -LiteralPath (Join-Path $env:TEMP 'matrix-robot-vps-public-url.txt') -Raw; [System.Windows.MessageBox]::Show(('Matrix Robot يعمل على ForexVPS.' + [Environment]::NewLine + [Environment]::NewLine + 'على الـ VPS:' + [Environment]::NewLine + 'http://127.0.0.1:8080' + [Environment]::NewLine + [Environment]::NewLine + 'الهاتف (آسيا سيل / أي شبكة):' + [Environment]::NewLine + $u.Trim() + [Environment]::NewLine + [Environment]::NewLine + 'Safari → مشاركة → إضافة إلى الشاشة الرئيسية.' + [Environment]::NewLine + 'الرابط يتغيّر عند إعادة التشغيل إلا إذا ثبّتّ نفقاً باسم ثابت لاحقاً.'), 'Matrix Robot VPS')"
) else (
  powershell -NoProfile -ExecutionPolicy Bypass -Command "Add-Type -AssemblyName PresentationFramework; [System.Windows.MessageBox]::Show(('الخدمات تعمل محلياً على :8080 لكن فشل الرابط العام.' + [Environment]::NewLine + '%LOG%'), 'Matrix Robot VPS')"
)

endlocal
exit /b 0
