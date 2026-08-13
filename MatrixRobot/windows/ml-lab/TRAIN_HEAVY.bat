@echo off
REM Heavy training on laptop RTX — writes ml_models\*.json for VPS
setlocal
cd /d "%~dp0..\..\artifacts\python-agents"
if not exist ".venv\Scripts\python.exe" (
  echo Run SETUP_ML_LAB.bat first
  pause
  exit /b 1
)

set MATRIX_ML_DIR=C:\MatrixML
set MATRIX_ML_MODEL_DIR=ml_models
set MATRIX_ML_DEVICE=auto

echo Starting HEAVY train (backtest labels + CUDA if available)...
".venv\Scripts\python.exe" scripts\train_signal_model.py --heavy --device auto --source backtest --symbols EURUSD,XAUUSD,GBPUSD,USDJPY,USDCAD

echo.
echo If you have closed-trade history, also run outcomes pass:
".venv\Scripts\python.exe" scripts\train_signal_model.py --heavy --device auto --source outcomes --symbols EURUSD,XAUUSD,GBPUSD,USDJPY

echo.
echo Next: PACK_FOR_VPS.bat
pause
