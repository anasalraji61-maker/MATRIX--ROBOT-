@echo off
setlocal EnableExtensions
cd /d "%~dp0.."
set "ROOT=%CD%"
set "LOG=%TEMP%\matrix-robot-start.log"

echo ===== %DATE% %TIME% =====> "%LOG%"
echo ROOT=%ROOT%>> "%LOG%"

REM Make node/npm/pnpm visible when launched from Explorer/Desktop
set "PATH=%ProgramFiles%\nodejs;%ProgramFiles(x86)%\nodejs;%APPDATA%\npm;%LOCALAPPDATA%\pnpm;%USERPROFILE%\.local\bin;%PATH%"

where node >> "%LOG%" 2>&1
where pnpm.cmd >> "%LOG%" 2>&1
where npm.cmd >> "%LOG%" 2>&1

if not exist "%ROOT%\.env" (
  echo Missing .env at %ROOT%\.env>> "%LOG%"
  powershell -NoProfile -Command "Add-Type -AssemblyName PresentationFramework; [System.Windows.MessageBox]::Show('ملف .env غير موجود. ضع المفاتيح أولاً.','Matrix Robot')"
  exit /b 1
)

REM Ensure Zod v3 compatibility for generated schemas
if exist "lib\api-zod\src\generated\api.ts" (
  powershell -NoProfile -ExecutionPolicy Bypass -Command ^
    "(Get-Content -LiteralPath 'lib\api-zod\src\generated\api.ts' -Raw) -replace 'zod\.looseObject','zod.object' | Set-Content -LiteralPath 'lib\api-zod\src\generated\api.ts' -NoNewline" >> "%LOG%" 2>&1
)

REM Free old listeners if leftover
for /f "tokens=5" %%P in ('netstat -ano ^| findstr ":8080" ^| findstr LISTENING') do taskkill /PID %%P /F >> "%LOG%" 2>&1
for /f "tokens=5" %%P in ('netstat -ano ^| findstr ":5173" ^| findstr LISTENING') do taskkill /PID %%P /F >> "%LOG%" 2>&1

REM Build API if missing
if not exist "artifacts\api-server\dist\index.mjs" (
  echo Building API...>> "%LOG%"
  pushd "artifacts\api-server"
  node ".\build.mjs" >> "%LOG%" 2>&1
  if errorlevel 1 (
    popd
    powershell -NoProfile -Command "Add-Type -AssemblyName PresentationFramework; [System.Windows.MessageBox]::Show('فشل بناء API. راجع السجل: %LOG%','Matrix Robot')"
    exit /b 1
  )
  popd
)

REM Start API hidden via PowerShell process
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "Start-Process -WindowStyle Hidden -WorkingDirectory '%ROOT%\artifacts\api-server' -FilePath 'node' -ArgumentList '--env-file=..\..\.env','--enable-source-maps','.\dist\index.mjs'" >> "%LOG%" 2>&1

REM Start Dashboard hidden via PowerShell process
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$env:PORT='5173'; $env:BASE_PATH='/'; Start-Process -WindowStyle Hidden -WorkingDirectory '%ROOT%' -FilePath 'pnpm.cmd' -ArgumentList '--filter','@workspace/dashboard','run','dev'" >> "%LOG%" 2>&1

REM Wait until port 5173 is listening (max ~30s)
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$ok=$false; 1..30 | ForEach-Object { Start-Sleep -Seconds 1; $c=Get-NetTCPConnection -LocalPort 5173 -State Listen -ErrorAction SilentlyContinue; if($c){$ok=$true; break} }; if(-not $ok){ exit 1 }" >> "%LOG%" 2>&1
if errorlevel 1 (
  powershell -NoProfile -Command "Add-Type -AssemblyName PresentationFramework; [System.Windows.MessageBox]::Show('تعذر تشغيل الواجهة. راجع السجل: %LOG%','Matrix Robot')"
  exit /b 1
)

REM Detect LAN IP for phone access
for /f "tokens=2 delims=:" %%A in ('ipconfig ^| findstr /c:"IPv4"') do (
  for /f "tokens=1" %%B in ("%%A") do set "LANIP=%%B"
)
if defined LANIP (
  echo Phone URL: http://%LANIP%:5173>> "%LOG%"
  start "" "http://localhost:5173/"
  powershell -NoProfile -Command "Add-Type -AssemblyName PresentationFramework; [System.Windows.MessageBox]::Show('Matrix Robot يعمل الآن.%0Aاللابتوب: http://localhost:5173%0Aالهاتف (نفس الواي فاي): http://%LANIP%:5173','Matrix Robot')"
) else (
  start "" "http://localhost:5173/"
)

endlocal
exit /b 0
