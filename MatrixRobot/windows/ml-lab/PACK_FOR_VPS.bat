@echo off
REM Pack trained models for copy to ForexVPS
setlocal
cd /d "%~dp0..\..\artifacts\python-agents"
set OUT=C:\MatrixML\deploy_to_vps
mkdir "%OUT%" 2>nul
mkdir "%OUT%\ml_models" 2>nul

if exist ml_models\signal_deploy.json (
  copy /Y ml_models\signal_deploy.json "%OUT%\ml_models\signal_deploy.json" >nul
)
copy /Y ml_models\*.json "%OUT%\ml_models\" >nul 2>nul
copy /Y ml_models\*.pt "%OUT%\ml_models\" >nul 2>nul

copy /Y "%~dp0VPS_ML_ENV.txt" "%OUT%\VPS_ML_ENV.txt" >nul

echo.
echo Packed to: %OUT%
echo 1) Copy folder ml_models to VPS:
echo    C:\MatrixRobot-Updated\MatrixRobot\artifacts\python-agents\ml_models\
echo 2) Append lines from VPS_ML_ENV.txt into VPS .env
echo 3) Restart Brain on VPS
echo.
dir /b "%OUT%\ml_models"
pause
