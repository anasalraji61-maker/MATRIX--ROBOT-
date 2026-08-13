@echo off
setlocal EnableExtensions
cd /d "%~dp0.."
set "ROOT=%CD%"
set "LOG=%TEMP%\matrix-robot-start.log"
set "URLFILE=%TEMP%\matrix-robot-public-url.txt"
set "PUBLICURL="

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

REM Public HTTPS tunnel so iPhone works on Asia cell / any network (not Wi-Fi only)
REM For 24/7 permanent hosting prefer ForexVPS: windows\vps\install-forexvps.bat
echo Starting public phone tunnel...>> "%LOG%"
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0start-public-tunnel.ps1" >> "%LOG%" 2>&1
if exist "%URLFILE%" (
  set /p PUBLICURL=<"%URLFILE%"
)

start "" "http://localhost:5173/"

if defined PUBLICURL (
  echo Phone public URL: %PUBLICURL%>> "%LOG%"
  powershell -NoProfile -ExecutionPolicy Bypass -Command "Add-Type -AssemblyName PresentationFramework; $u = Get-Content -LiteralPath (Join-Path $env:TEMP 'matrix-robot-public-url.txt') -Raw; [System.Windows.MessageBox]::Show(('Matrix Robot يعمل الآن.' + [Environment]::NewLine + [Environment]::NewLine + 'اللابتوب:' + [Environment]::NewLine + 'http://localhost:5173' + [Environment]::NewLine + [Environment]::NewLine + 'الهاتف من أي شبكة (آسيا سيل / بيانات الجوال):' + [Environment]::NewLine + $u.Trim() + [Environment]::NewLine + [Environment]::NewLine + 'افتح الرابط في Safari ثم شارك ← إضافة إلى الشاشة الرئيسية.'), 'Matrix Robot')"
) else (
  echo Tunnel failed — see log>> "%LOG%"
  powershell -NoProfile -ExecutionPolicy Bypass -Command "Add-Type -AssemblyName PresentationFramework; [System.Windows.MessageBox]::Show(('الواجهة تعمل على اللابتوب، لكن فشل إنشاء الرابط العام للهاتف.' + [Environment]::NewLine + 'راجع السجل:' + [Environment]::NewLine + '%LOG%'), 'Matrix Robot')"
)

endlocal
exit /b 0
