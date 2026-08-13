@echo off
chcp 65001 >nul
title V11 — تثبيت التحديث التلقائي كل ساعة
color 0A

net session >nul 2>&1
if %errorLevel% neq 0 (
    echo.
    echo  [خطأ] شغّل هذا الملف كـ Administrator:
    echo         كليك يمين ^> Run as administrator
    echo.
    pause
    exit /b 1
)

set "PYROOT=C:\MatrixRobot\MatrixRobot\MatrixRobot\artifacts\python-agents"
set "SCRIPT=%PYROOT%\scripts\GENERATE_V11_TRADE_REVIEW.ps1"
set "TASK=MatrixV11HourlyTradeReport"

echo.
echo  ========================================
echo   V11 — تثبيت التحديث التلقائي كل ساعة
echo  ========================================
echo.

if not exist "%SCRIPT%" (
    echo  [خطأ] الملف غير موجود:
    echo  %SCRIPT%
    echo.
    echo  انسخ مجلد scripts من اللابتوب أو أعد فك v11_surgical_hotfix.zip
    pause
    exit /b 1
)

echo  [1/3] حذف مهمة قديمة إن وُجدت...
schtasks /Delete /TN "%TASK%" /F >nul 2>&1

echo  [2/3] إنشاء مهمة Windows — كل ساعة...
schtasks /Create /TN "%TASK%" /TR "powershell.exe -NoProfile -ExecutionPolicy Bypass -File \"%SCRIPT%\" -ArchiveHourly" /SC HOURLY /MO 1 /F
if %errorLevel% neq 0 (
    echo.
    echo  [فشل] لم تُنشأ المهمة. جرّب مرة أخرى كـ Administrator.
    pause
    exit /b 1
)

echo  [3/3] تشغيل التقرير الآن (أول تحديث)...
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%SCRIPT%" -ArchiveHourly
if %errorLevel% neq 0 (
    echo.
    echo  [تحذير] المهمة مُثبتة لكن التشغيل الأول فشل.
    echo  تأكد أن Brain يعمل مرة واحدة: START_BRAIN.bat
    pause
    exit /b 1
)

echo.
echo  ========================================
echo   تم — لن تحتاج PowerShell بعد اليوم
echo  ========================================
echo.
echo  الملف يتحدّث وحده كل ساعة:
echo  %PYROOT%\V11_TRADE_REVIEW_REPORT.md
echo.
echo  افتحه بـ Notepad وانسخ — فقط.
echo.
echo  للتحقق: شغّل CHECK_HOURLY_REPORT.bat
echo.
pause
