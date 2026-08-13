@echo off
chcp 65001 >nul
title V11 — حالة التحديث التلقائي
color 0B

set "PYROOT=C:\MatrixRobot\MatrixRobot\MatrixRobot\artifacts\python-agents"
set "REPORT=%PYROOT%\V11_TRADE_REVIEW_REPORT.md"
set "TASK=MatrixV11HourlyTradeReport"

echo.
echo  === حالة جدولة التقرير ===
echo.

schtasks /Query /TN "%TASK%" /FO LIST 2>nul | findstr /I "TaskName Status Next"
if %errorLevel% neq 0 (
    echo  [غير مُثبت] شغّل INSTALL_HOURLY_REPORT.bat كـ Administrator
) else (
    echo.
    echo  [مُثبت] التحديث التلقائي يعمل كل ساعة
)

echo.
if exist "%REPORT%" (
    for %%F in ("%REPORT%") do echo  آخر تعديل للتقرير: %%~tF
    echo  المسار: %REPORT%
) else (
    echo  [لا يوجد تقرير بعد] شغّل INSTALL_HOURLY_REPORT.bat
)

echo.
echo  آخر سجل:
set "LOGDIR=%PYROOT%\reports\scheduler"
if exist "%LOGDIR%" (
    dir /O-D /B "%LOGDIR%\generate_*.log" 2>nul | findstr /N "^" | findstr "^1:" 
)
echo.
pause
