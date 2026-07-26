# إدارة حسابين معاً — FN Demo + حساب حقيقي صغير

## كيف يعمل؟

```
Brain (دورة واحدة) → نفس الإشارة
        ↓
   ┌────┴────┐
   ↓         ↓
Primary    Secondary
FN Demo    Real $81
Bridge     Bridge
:5555      :5556
```

- **تحليل واحد** (OpenRouter مرة واحدة)
- **تنفيذ منفصل** لكل حساب حسب رصيده ومخاطره
- كل حساب له: equity خاص، DD خاص، لوت خاص، صفقات مفتوحة منفصلة

---

## المتطلبات

| # | ماذا تحتاج |
|---|-----------|
| 1 | **MT5 مرتين** — مرة لكل شركة (أو جهازين) |
| 2 | **Bridge مرتين** — منفذ 5555 و 5556 |
| 3 | `ACCOUNTS_JSON` في `.env` للحساب الثاني |
| 4 | إعادة تشغيل Brain بعد التعديل |

---

## الخطوة 1 — Bridge ثاني للحساب الحقيقي

### على نفس VPS (إن أمكن)

1. ثبّت MT5 ثانٍ أو portable MT5 لشركة الحساب الحقيقي
2. سجّل الدخول بحساب الـ $81
3. افتح PowerShell **جديد**:

```powershell
cd C:\MatrixRobot\MatrixRobot\MatrixRobot\artifacts\python-agents
$env:BRIDGE_PORT="5556"
$env:MT5_LOGIN="رقم_حسابك_الحقيقي"
$env:MT5_PASSWORD="كلمة_المرور"
$env:MT5_SERVER="اسم_السيرفر"
$env:MT5_BRIDGE_SECRET="نفس_السر_في_.env"
python mt5_windows_bridge.py
```

### إن كان الحساب الحقيقي على جهاز آخر

- شغّل Bridge هناك على منفذ 5555
- استخدم IP الجهاز في `bridge_url` (مثلاً `http://192.168.x.x:5555`)

---

## الخطوة 2 — أضف ACCOUNTS_JSON في `.env`

افتح:
```
C:\MatrixRobot\MatrixRobot\MatrixRobot\.env
```

أضف سطراً **واحداً** (بدون أسطر جديدة داخل JSON):

```env
ACCOUNTS_JSON=[{"id":"real_micro","label":"Real $81","bridge_url":"http://127.0.0.1:5556","account_profile":"REAL","risk_per_trade_pct":3.0,"max_daily_drawdown_pct":15,"max_total_drawdown_pct":25,"max_concurrent_positions":1,"max_trades_per_day":5,"min_conviction_threshold":0.65,"symbols":"EURUSD,GBPUSD,USDJPY,USDCAD","prop_firm":"","starting_balance":81,"enabled":true}]
```

انسخ نفس السطر إلى:
```
artifacts\python-agents\.env
```

---

## ماذا يعني كل حقل؟

| الحقل | FN Demo (primary) | Real $81 (secondary) |
|-------|-------------------|----------------------|
| `bridge_url` | :5555 (من MT5_BRIDGE_URL) | :5556 |
| `account_profile` | FN_CHALLENGE (عام) | REAL |
| `risk_per_trade_pct` | 0.8% | 3.0% (micro) |
| `max_concurrent_positions` | 5 | 1 |
| `max_trades_per_day` | 20 | 5 |
| `symbols` | الكل (24) | فوركس فقط (بدون ذهب) |
| `starting_balance` | تلقائي | 81 |

---

## الخطوة 3 — أعد تشغيل Brain

```powershell
# أوقف uvicorn ثم:
cd C:\MatrixRobot\MatrixRobot\MatrixRobot\artifacts\python-agents
.\.venv\Scripts\activate
uvicorn main:app --host 0.0.0.0 --port 8000
```

---

## التحقق

```
http://127.0.0.1:8080/api/agents/accounts
```

يجب أن ترى **حسابين**:
- `primary` — FN Demo
- `real_micro` — Real $81

---

## ملاحظات مهمة

1. **Primary يبقى FN** — لا تغيّر `ACCOUNT_PROFILE` العام إذا تريد FN على الديمو
2. **الحساب الصغير REAL** — يستخدم micro sizing تلقائياً (equity ≤ $100)
3. **لا ذهب على $81** — `symbols` يقيّد الفوركس فقط
4. **MT5 على الهاتف** — كل حساب في تطبيق منفصل أو نفس التطبيق بحسابين

---

## تحذير

حساب $81 **صغير جداً**. حتى مع الإعدادات الآمنة، خسارة سريعة ممكنة.  
استمر 3 أسابيع على الديمو — الحساب الحقيقي **اختياري** وليس عاجلاً.
