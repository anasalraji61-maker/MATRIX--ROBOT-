@echo off
setlocal
set "ROOT=%~dp0.."
cd /d "%ROOT%"

REM Ensure generated Zod schemas work on Zod v3
if exist "lib\api-zod\src\generated\api.ts" (
  powershell -NoProfile -ExecutionPolicy Bypass -Command ^
    "(Get-Content -LiteralPath 'lib\api-zod\src\generated\api.ts' -Raw) -replace 'zod\.looseObject','zod.object' | Set-Content -LiteralPath 'lib\api-zod\src\generated\api.ts' -NoNewline" >nul 2>&1
)

REM Build API once if missing
if not exist "artifacts\api-server\dist\index.mjs" (
  pushd "artifacts\api-server"
  node ".\build.mjs"
  if errorlevel 1 (
    echo API build failed.
    pause
    exit /b 1
  )
  popd
)

REM Start API minimized
start "MatrixRobot-API" /min cmd /c "cd /d \"%ROOT%\artifacts\api-server\" && node --env-file=..\..\.env --enable-source-maps .\dist\index.mjs"

REM Start Dashboard minimized
start "MatrixRobot-Dashboard" /min cmd /c "cd /d \"%ROOT%\" && set PORT=5173&& set BASE_PATH=/&& pnpm.cmd --filter @workspace/dashboard run dev"

REM Wait for servers, then open UI
timeout /t 6 /nobreak >nul
start "" "http://localhost:5173/"
endlocal
