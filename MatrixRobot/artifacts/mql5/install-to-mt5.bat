@echo off
setlocal EnableExtensions
set "SRC=%~dp0Experts\MatrixGuard.mq5"
if not exist "%SRC%" (
  echo Missing %SRC%
  pause
  exit /b 1
)

set "BASE=%APPDATA%\MetaQuotes\Terminal"
if not exist "%BASE%" (
  echo MetaTrader Terminal folder not found:
  echo   %BASE%
  echo Install MT5 or copy MatrixGuard.mq5 manually into MQL5\Experts
  pause
  exit /b 1
)

set "COPIED=0"
for /d %%D in ("%BASE%\*") do (
  if exist "%%D\MQL5\Experts" (
    copy /Y "%SRC%" "%%D\MQL5\Experts\MatrixGuard.mq5" >nul
    echo Copied to: %%D\MQL5\Experts\MatrixGuard.mq5
    set "COPIED=1"
  )
)

if "%COPIED%"=="0" (
  echo No MQL5\Experts folders found under %BASE%
  pause
  exit /b 1
)

echo.
echo Next:
echo  1) Open MetaEditor -^> MatrixGuard.mq5 -^> F7 Compile
echo  2) MT5 Options -^> Expert Advisors -^> allow WebRequest for http://127.0.0.1:5555
echo  3) Attach MatrixGuard to any chart ^(protective only^)
pause
endlocal
