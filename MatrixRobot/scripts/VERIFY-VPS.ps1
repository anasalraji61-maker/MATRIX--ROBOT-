# Matrix Robot — فحص سريع للمنظومة على VPS
# شغّله من PowerShell على الـ VPS:
#   cd C:\MatrixRobot\MatrixRobot\MatrixRobot\scripts
#   .\VERIFY-VPS.ps1

$ErrorActionPreference = "Continue"
$secret = $env:MT5_BRIDGE_SECRET

function Test-Url($label, $url, $headers = @{}) {
    Write-Host "`n=== $label ===" -ForegroundColor Cyan
    try {
        $r = Invoke-RestMethod -Uri $url -Headers $headers -TimeoutSec 15
        $r | ConvertTo-Json -Depth 6
        return $true
    } catch {
        Write-Host "FAIL: $($_.Exception.Message)" -ForegroundColor Red
        return $false
    }
}

function Test-Bridge($port) {
    Write-Host "`n=== Bridge port $port ===" -ForegroundColor Cyan
    $h = @{}
    if ($secret) { $h["X-Bridge-Secret"] = $secret }
    try {
        $r = Invoke-RestMethod -Uri "http://127.0.0.1:$port/health" -Headers $h -TimeoutSec 10
        $r | ConvertTo-Json -Depth 4
        return $true
    } catch {
        Write-Host "FAIL (Bridge $port غير شغال أو بدون سر): $($_.Exception.Message)" -ForegroundColor Red
        return $false
    }
}

Write-Host "Matrix Robot VPS Health Check" -ForegroundColor Green
Write-Host "Time: $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')"

$b5555 = Test-Bridge 5555
$b5556 = Test-Bridge 5556

Test-Url "Scheduler" "http://127.0.0.1:8080/api/agents/scheduler/status"
Test-Url "Cycle (last)" "http://127.0.0.1:8080/api/agents/cycle/status"
Test-Url "Positions (primary)" "http://127.0.0.1:8080/api/agents/positions/live"
Test-Url "Accounts" "http://127.0.0.1:8080/api/agents/accounts"

Write-Host "`n=== Summary ===" -ForegroundColor Yellow
if ($b5555) { Write-Host "Bridge 5555 (FN Demo)     : OK" -ForegroundColor Green }
else         { Write-Host "Bridge 5555 (FN Demo)     : DOWN — أعد تشغيل Bridge الأول" -ForegroundColor Red }
if ($b5556) { Write-Host "Bridge 5556 (ForexIraq)   : OK" -ForegroundColor Green }
else         { Write-Host "Bridge 5556 (ForexIraq)   : DOWN — طبيعي حتى تُشغّل Bridge الثاني" -ForegroundColor Yellow }

Write-Host "`nملاحظة: عدم صفقات على الهاتف طبيعي إذا:"
Write-Host "  - الدورة الأخيرة قررت HOLD"
Write-Host "  - لا صفقات مفتوحة حالياً (آخر صفقة أُغلقت)"
Write-Host "  - هاتفك على ForexIraq ولم يُفعّل ACCOUNTS_JSON بعد"
