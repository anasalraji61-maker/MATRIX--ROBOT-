# Matrix Robot — ForexVPS Phase 1 (بدون .env)
# شغّل كـ Administrator على السيرفر الجديد بعد RDP
$ErrorActionPreference = "Continue"
Write-Host "=== Matrix Robot — ForexVPS Phase 1 ===" -ForegroundColor Cyan

# 1) أدوات أساسية
winget install Git.Git OpenJS.NodeJS.LTS Python.Python.3.12 --accept-package-agreements --accept-source-agreements
npm install -g pnpm

Write-Host "`n>>> أعد فتح PowerShell كـ Administrator ثم شغّل Phase 1b <<<" -ForegroundColor Yellow
