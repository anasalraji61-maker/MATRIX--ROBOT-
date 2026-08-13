@echo off
REM Matrix ML Lab — one-time setup on the LAPTOP (RTX 8GB / 32GB RAM)
setlocal
cd /d "%~dp0..\..\artifacts\python-agents"
if errorlevel 1 (
  echo Cannot find artifacts\python-agents
  pause
  exit /b 1
)

if not exist ".venv\Scripts\python.exe" (
  echo Creating .venv ...
  python -m venv .venv
)

echo Installing PyTorch CUDA 12.4 wheel for RTX ...
".venv\Scripts\python.exe" -m pip install --upgrade pip
".venv\Scripts\python.exe" -m pip install torch torchvision --index-url https://download.pytorch.org/whl/cu124
if errorlevel 1 (
  echo CUDA wheel failed — trying CPU torch as fallback
  ".venv\Scripts\python.exe" -m pip install torch --index-url https://download.pytorch.org/whl/cpu
)

echo Installing MLflow + sklearn ...
".venv\Scripts\python.exe" -m pip install -r requirements-ml.txt
".venv\Scripts\python.exe" -m pip install -r requirements.txt

mkdir C:\MatrixML 2>nul
mkdir ml_models 2>nul

echo.
echo === CUDA check ===
".venv\Scripts\python.exe" -c "import torch; print('torch', torch.__version__); print('cuda', torch.cuda.is_available()); print(torch.cuda.get_device_name(0) if torch.cuda.is_available() else 'CPU only')"
echo.
echo Setup done. Next: run TRAIN_HEAVY.bat
pause
