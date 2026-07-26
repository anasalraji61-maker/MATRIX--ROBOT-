@echo off
REM Matrix Robot — weekly portfolio backtest (24 symbols, 5000 H1 bars)
REM Does NOT touch Brain / MT5. Safe to run via Task Scheduler.
REM Logs: C:\MatrixRobot\backtest_logs\

setlocal
set ROOT=C:\MatrixRobot\MatrixRobot\MatrixRobot\artifacts\python-agents
set VENV=C:\MatrixVenv\Scripts\python.exe
set LOGDIR=C:\MatrixRobot\backtest_logs
set SYMBOLS=EURUSD,GBPUSD,USDJPY,USDCHF,AUDUSD,NZDUSD,USDCAD,EURGBP,EURJPY,GBPJPY,EURAUD,EURCHF,AUDJPY,CHFJPY,CADJPY,NZDJPY,GBPCHF,AUDCAD,AUDNZD,XAUUSD,XAGUSD,US30,US500,USTEC

if not exist "%LOGDIR%" mkdir "%LOGDIR%"

for /f "tokens=1-3 delims=/ " %%a in ('date /t') do set STAMP=%%c%%b%%a
set LOGFILE=%LOGDIR%\weekly_%STAMP%.log

echo ================================================== >> "%LOGFILE%"
echo Weekly backtest started: %date% %time% >> "%LOGFILE%"
echo ================================================== >> "%LOGFILE%"

cd /d "%ROOT%"
"%VENV%" scripts\run_portfolio_report.py --bars 5000 --symbols %SYMBOLS% >> "%LOGFILE%" 2>&1

echo Finished: %date% %time% >> "%LOGFILE%"
echo Report folder: %ROOT%\backtest_reports >> "%LOGFILE%"

endlocal
