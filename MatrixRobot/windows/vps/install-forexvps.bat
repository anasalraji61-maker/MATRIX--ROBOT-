@echo off
setlocal EnableExtensions
cd /d "%~dp0..\.."
set "ROOT=%CD%"
set "LOG=%TEMP%\matrix-robot-vps-install.log"

echo ===== ForexVPS install %DATE% %TIME% =====> "%LOG%"
echo ROOT=%ROOT%>> "%LOG%"

set "PATH=%ProgramFiles%\nodejs;%ProgramFiles(x86)%\nodejs;%APPDATA%\npm;%LOCALAPPDATA%\pnpm;%USERPROFILE%\.local\bin;%PATH%"

echo.
echo ============================================
echo   Matrix Robot - ForexVPS one-time install
echo ============================================
echo.
echo Log: %LOG%
echo.

if not exist "%ROOT%\.env" (
  echo [!] Missing .env
  echo Copy .env from the laptop to:
  echo   %ROOT%\.env
  echo Then run this installer again.
  pause
  exit /b 1
)

where node >nul 2>&1
if errorlevel 1 (
  echo [!] Node.js not found. Install Node LTS from https://nodejs.org then retry.
  pause
  exit /b 1
)

where pnpm.cmd >nul 2>&1
if errorlevel 1 (
  echo Installing pnpm...
  npm install -g pnpm >> "%LOG%" 2>&1
)

echo [1/4] Aligning .env for co-located ForexVPS...
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0ensure-vps-env.ps1" -Root "%ROOT%" >> "%LOG%" 2>&1
if errorlevel 1 (
  echo Failed to prepare .env — see %LOG%
  pause
  exit /b 1
)

echo [2/4] Installing npm packages (ignore-scripts for Windows)...
call pnpm install --ignore-scripts >> "%LOG%" 2>&1
if errorlevel 1 (
  echo pnpm install failed — see %LOG%
  pause
  exit /b 1
)

if exist "lib\api-zod\src\generated\api.ts" (
  powershell -NoProfile -ExecutionPolicy Bypass -Command ^
    "(Get-Content -LiteralPath 'lib\api-zod\src\generated\api.ts' -Raw) -replace 'zod\.looseObject','zod.object' | Set-Content -LiteralPath 'lib\api-zod\src\generated\api.ts' -NoNewline" >> "%LOG%" 2>&1
)

echo [3/4] Building API...
pushd "artifacts\api-server"
node ".\build.mjs" >> "%LOG%" 2>&1
if errorlevel 1 (
  popd
  echo API build failed — see %LOG%
  pause
  exit /b 1
)
popd

echo [4/4] Building Dashboard...
set "PORT=5173"
set "BASE_PATH=/"
call pnpm --filter @workspace/dashboard run build >> "%LOG%" 2>&1
if errorlevel 1 (
  echo Dashboard build failed — see %LOG%
  pause
  exit /b 1
)

echo.
echo Install OK.
echo Next: double-click start-forexvps.bat
echo Optional: install-autostart.bat  (start on Windows logon)
echo.
pause
endlocal
exit /b 0
