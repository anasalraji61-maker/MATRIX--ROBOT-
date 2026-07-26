# V12 ML Lab — خطة التعلم القوي (بعد نجاح V11)

> **تاريخ الإنشاء:** 2026-06-24  
> **الحالة:** مخطط — لا تُنفَّذ قبل استقرار V11 لـ 4–8 أسابيع  
> **القرار:** نسخة منفصلة عن V11 Production — لا تعديل على الروبوت الرابح مباشرة

---

## الفكرة الأساسية

```
V11 Production Demo  →  الربح والاستقرار (تعديلات جراحية فقط)
V12 ML Lab           →  تجارب، تعلم قوي، فشل مسموح
```

**النجاح = ما يثبت في V12 ينتقل جراحيًا إلى V11.**

---

## متى نبدأ V12؟ (شروط البوابة)

| # | الشرط | الهدف |
|---|--------|--------|
| 1 | V11 ديمو **4–8 أسابيع** بـ PF ≥ 1.5 | استقرار مثبت |
| 2 | **500+** صفقة مغلقة ببيانات نظيفة | strategy, strength, spread, SL/TP |
| 3 | logging يعمل في التقرير اليومي | ليس unknown |
| 4 | حساب MT5 **ديمو ثانٍ** جاهز | عزل التجارب عن V11 |
| 5 | baseline محفوظ | V11_TRADE_REVIEW_BEFORE + AFTER |

**لا تبدأ V12 إذا:** PF V11 تحت 1.3 لأسبوعين، أو strategy ما زال unknown.

---

## هيكل المجلد المقترح

```
C:\MatrixRobot\MatrixRobot\MatrixRobot\artifacts\
├── python-agents\              ← V11 Production (لا تلمسه بقوة)
└── python-agents-v12-ml-lab\   ← نسخة التجارب
    ├── .env                    ← إعدادات ML/RL قوية
    ├── ml_models\
    ├── ml\                     ← PyTorch + trainer + RL
    ├── .state\rl_policy.json
    └── reports\
```

---

## المرحلة 0 — نسخ V11 → V12 (يوم واحد)

```powershell
$src = "C:\MatrixRobot\MatrixRobot\MatrixRobot\artifacts\python-agents"
$dst = "C:\MatrixRobot\MatrixRobot\MatrixRobot\artifacts\python-agents-v12-ml-lab"
Copy-Item -Recurse -Force $src $dst
# عدّل .env في V12 فقط — لا تلمس V11
```

- حساب MT5 ديمو **جديد** في `.env` لـ V12
- منفذ مختلف إن شغّلت الاثنين على نفس VPS: `--port 8001`
- قاعدة بيانات منفصلة أو schema `v12_` (اختياري)

---

## المرحلة 1 — V11 يثبت نفسه (الأسابيع 1–4)

**ما يعمل على V11 فقط:**

```env
ML_FILTER_MODE=advisory
ML_RETRAIN_ENABLED=false
RL_MODE=shadow
SYMBOL_QUARANTINE=GBPCHF,CADCHF
```

**مراجعة أسبوعية:**
- تقرير `V11_TRADE_REVIEW_REPORT.md`
- `/agents/ml/status` — rl.total_updates يزيد
- PF، Win Rate، أسوأ رموز/أوقات

---

## المرحلة 2 — تفعيل تدريجي على V12 (الأسابيع 4–6)

### أسبوع 1 على V12: ML retrain فقط

```env
ML_FILTER_MODE=advisory
ML_RETRAIN_ENABLED=true
ML_RETRAIN_INTERVAL_HOURS=168
RL_MODE=shadow
```

```powershell
pip install -r requirements-ml.txt
python scripts/train_signal_model.py
mlflow ui --backend-store-uri sqlite:///C:/MatrixML/mlflow.db
```

### أسبوع 2 على V12: ML enforce ناعم

```env
ML_FILTER_MODE=enforce
ML_MIN_WIN_PROB=0.35
```

يمنع فقط الصفقات **الضعيفة جدًا** — ليس كل شيء تحت 0.45.

### أسبوع 3–4 على V12: RL enforce

```env
RL_MODE=enforce
RL_MIN_Q_VALUE=-0.10
```

بعد **300+** صفقة على V12 مع logging نظيف.

---

## المرحلة 3 — RL أعمق (الشهر 2–3 على V12)

| الأداة | الاستخدام | مفتوح المصدر |
|--------|-----------|--------------|
| PyTorch | تصنيف win/loss | ✅ |
| MLflow | تتبع التجارب | ✅ |
| scikit-learn | baseline سريع | ✅ |
| Stable-Baselines3 | PPO / DQN | ✅ |
| Gymnasium | بيئة محاكاة | ✅ |
| Pandas / NumPy | datasets | ✅ |
| Hugging Face | أخبار (اختياري) | ✅ |

**ترتيب التجربة:**
1. رمز واحد (EURUSD أو XAGUSD)
2. بيئة Gymnasium مبسطة
3. SB3 PPO على بيانات V11/V12 التاريخية
4. مقارنة مع bandit الحالي

**لا Deep RL على حساب حي قبل شهر ديمو في المختبر.**

---

## ما لا تفعّله أبدًا مبكرًا

```env
# ❌ على V11 Production
ML_RETRAIN_INTERVAL_HOURS=1
ML_FILTER_MODE=enforce          # قبل إثبات advisory
RL_MODE=enforce                 # قبل 300–500 صفقة نظيفة
DEEP_RL_IN_LIVE_LOOP=true
PYTORCH_IN_EVERY_TRADE_DECISION=true
```

---

## Dataset المطلوب (لكل صفقة)

| الحقل | لماذا |
|-------|--------|
| trade_style / trade_tier | scalping vs intraday |
| strategy_name | أي استراتيجية |
| strength | جودة الإشارة |
| spread_at_entry | تكلفة الدخول |
| SL / TP | مخاطرة |
| hold_minutes | نوع الصفقة |
| council_score, skeptic_vote | قرار المجلس |
| close_reason | SL / TP / manual |
| filter_rejected + reason | لماذا مُنعت صفقة |

> إصلاح logging على V11 هو **شرط مسبق** لنجاح V12.

---

## مقارنة V11 vs V12 (أسبوعي)

| Metric | V11 | V12 | قرار |
|--------|-----|-----|------|
| Net Profit | | | |
| Profit Factor | | | |
| Win Rate | | | |
| Trades/day | | | |
| Max drawdown | | | |
| ML blocks/day | | | |
| RL blocks/day | | | |

**قاعدة النقل:** ميزة V12 تنتقل لـ V11 فقط إذا حسّنت PF أو قلّلت max loss **بدون** خفض الصفقات الرابحة > 20%.

---

## الجدول الزمني المختصر

| متى | ماذا |
|-----|------|
| **الآن – 4 أسابيع** | V11 فقط — حزمة جراحية + advisory + shadow |
| **أسبوع 4** | نسخ → `python-agents-v12-ml-lab` |
| **أسبوع 5–6** | V12: ML retrain أسبوعي |
| **أسبوع 7–8** | V12: ML enforce ناعم |
| **أسبوع 9–10** | V12: RL enforce |
| **شهر 3+** | V12: SB3 / Gymnasium تجريبي |
| **شهر 4+** | دمج الناجح → V11 جراحيًا |

---

## أوامر مفيدة

### تقرير V11
```powershell
cd C:\MatrixRobot\MatrixRobot\MatrixRobot\artifacts\python-agents
$env:PYTHONPATH="."
.\.venv\Scripts\python.exe -m tools.v11_trade_review_report -o V11_TRADE_REVIEW_REPORT.md
```

### ML status
```
http://127.0.0.1:8000/agents/ml/status
```

### تدريب يدوي (V12 لاحقًا)
```powershell
cd C:\MatrixRobot\...\python-agents-v12-ml-lab
pip install -r requirements-ml.txt
python scripts/train_signal_model.py
python scripts/export_ml_model.py
```

---

## ملف `.env` جاهز لـ V12 (لا تطبّق على V11 الآن)

احفظ كـ `V12_ML_LAB.env.example` عند إنشاء المختبر:

```env
TRADING_MODE_PROFILE=FULL_POWER_DEMO
# حساب ديمو ثانٍ — غيّر القيم
# MT5_LOGIN=
# MT5_PASSWORD=
# MT5_SERVER=

ML_FILTER_ENABLED=true
ML_FILTER_MODE=advisory
ML_MIN_WIN_PROB=0.45
ML_RETRAIN_ENABLED=true
ML_RETRAIN_INTERVAL_HOURS=168
ML_RETRAIN_SYMBOLS=EURUSD,XAUUSD,GBPUSD,USDJPY,XAGUSD

RL_ENABLED=true
RL_MODE=shadow
RL_MIN_Q_VALUE=-0.10
RL_LEARNING_RATE=0.12

# بعد 4 أسابيع V12 — رقِّ تدريجيًا:
# ML_FILTER_MODE=enforce
# ML_MIN_WIN_PROB=0.35
# RL_MODE=enforce
```

---

## الخلاصة

| V11 | V12 |
|-----|-----|
| المال والاستقرار | المختبر |
| تعديلات جراحية | تعلم بقوة |
| advisory + shadow | enforce تدريجي |
| حساب ديمو 1 | حساب ديمو 2 |

**الصيغة الذهبية:** لا تُفسد ما يعمل — انسخ، جرّب، ثم انقل الناجح فقط.

---

*آخر تحديث: بعد تطبيق الحزمة الجراحية V11 — baseline +232.88$, PF 2.03*
