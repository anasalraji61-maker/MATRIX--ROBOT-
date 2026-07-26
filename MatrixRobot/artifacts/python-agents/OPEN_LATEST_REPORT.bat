@echo off
set "REPORT=C:\MatrixRobot\MatrixRobot\MatrixRobot\artifacts\python-agents\V11_TRADE_REVIEW_REPORT.md"
if not exist "%REPORT%" (
    echo التقرير غير موجود. شغّل INSTALL_HOURLY_REPORT.bat أولاً.
    pause
    exit /b 1
)
notepad "%REPORT%"
