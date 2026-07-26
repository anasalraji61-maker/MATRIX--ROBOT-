# إصلاح سريع: صفقة ذهب أُغلقت على MT5 لكن الذاكرة ما زالت تحسبها
# شغّله على VPS بعد نسخ data_agent.py و account_state.py المحدّثين، ثم أعد تشغيل Brain

Write-Host "=== 1) صفقات MT5 الحية (primary) ===" -ForegroundColor Cyan
try {
    $pos = Invoke-RestMethod "http://127.0.0.1:8080/api/agents/positions/live" -TimeoutSec 15
    $pos | ConvertTo-Json -Depth 5
    Write-Host "count = $($pos.count)" -ForegroundColor Yellow
} catch {
    Write-Host "FAIL: $($_.Exception.Message)" -ForegroundColor Red
}

Write-Host "`n=== 2) آخر دورة ===" -ForegroundColor Cyan
try {
    $cycle = Invoke-RestMethod "http://127.0.0.1:8080/api/agents/cycle/status" -TimeoutSec 15
    Write-Host "decision: $($cycle.decision.action) — $($cycle.decision.reasoning)" -ForegroundColor Yellow
    if ($cycle.prop_status) {
        Write-Host "margin_used_pct: $($cycle.prop_status.margin_used_pct)" -ForegroundColor Yellow
    }
} catch {
    Write-Host "FAIL: $($_.Exception.Message)" -ForegroundColor Red
}

Write-Host "`n=== ماذا تفعل؟ ===" -ForegroundColor Green
Write-Host "1. انسخ الملفين المحدّثين إلى VPS:"
Write-Host "   tools\account_state.py"
Write-Host "   agents\data_agent.py"
Write-Host "2. أعد تشغيل Brain (uvicorn) فقط"
Write-Host "3. انتظر الدورة التالية (كل 60 دقيقة) أو افتح:"
Write-Host "   http://127.0.0.1:8080/api/agents/cycle/status"
Write-Host "4. إذا margin_used_pct = 0 والقرار ليس margin cap — تم الإصلاح"
