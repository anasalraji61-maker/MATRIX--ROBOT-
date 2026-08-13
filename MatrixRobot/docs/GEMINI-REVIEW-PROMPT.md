# استشارة Gemini — Matrix Robot (3 خطوات فقط)

## الخطوة 1
افتح: **https://gemini.google.com**

## الخطوة 2
اضغط **Ctrl+A** على هذا الملف من السطر التالي (▼ ابدأ من هنا) حتى النهاية، ثم **Ctrl+C**

## الخطوة 3
الصق في Gemini واضغط Enter. انتظر الإجابة.

**(اختياري — دقة أعلى):** ارفع مع الرسالة هذه الملفات من مجلد المشروع:

**أساسية (5):**
- `artifacts/python-agents/agents/agentic_brain.py`
- `artifacts/python-agents/agents/graph.py`
- `artifacts/python-agents/tools/registry.py`
- `artifacts/python-agents/tools/sandbox.py`
- `artifacts/python-agents/tools/adaptive_policy.py`

**للدقة الأعلى (3 إضافية):**
- `artifacts/python-agents/agents/risk_agent.py`
- `artifacts/python-agents/tools/emergency_guard.py`
- `artifacts/python-agents/tools/market_hours.py`

---

▼ **انسخ من هنا ↓**

---

أنت مستشار تقني. راجع مشروع **Matrix Robot** (نظام تداول آلي على MT5 + LangGraph).

**مهم:**
- المالك يستخدم **FundedNext Stellar 2-Step** ويُعلِن رسمياً أنه يستخدم **EA/روبوت** (مسموح — FN تتوقع اتساق الاستراتيجية خلال التحدي).
- **لا تقترح:** anti-detection، تمويه بشري، أو **execution variance** بمعنى jitter / delay / randomization / skip-signal عشوائي لمحاكاة إنسان.
- **APE (Adaptive Policy Envelope) مسموح** — دفاعي فقط: REDUCE_RISK، PAUSE_SYMBOL، TIGHTEN_CONVICTION، SKIP_SESSION. لا تخلط APE مع execution variance المحذوف.
- **لا تطلب** `.env` أو API keys.
- **أجب بالعربية** (مصطلحات تقنية بالإنجليزية عند الحاجة).
- التنفيذ الفعلي يتم في **Cursor** — أنت للاستشارة فقط.

---

## ما هو المشروع

نظام تداول forex + metals + indices:

| المكوّن | التقنية | المنفذ |
|---------|---------|--------|
| Brain | Python FastAPI + LangGraph | 8000 |
| API | Node Express | 8080 |
| Dashboard | React Vite | 5173 |
| MT5 Bridge | Python HTTP | 5555 |

- **بيانات:** Twelve Data (Grow, 55 req/min)
- **LLM:** OpenRouter Claude Sonnet 4.5 (الدماغ) + GPT-4o-mini (المشرف)
- **مجدول:** دورة كل 60 دقيقة
- **عطلة:** لا تحليل ولا OpenRouter السبت/الأحد UTC (`market_hours.py`)
- **وضع:** ACTIVE على VPS demo

---

## Pipeline (كل دورة)

```
emergency → data_fetch → sentiment → analysis (agentic_brain) → risk → supervisor → execution أو skip
```

| العقدة | الملف | الدور |
|--------|------|------|
| emergency | emergency_guard.py | عطلة نهاية الأسبوع، DD يومي، إيقاف قبل LLM |
| data_fetch | data_agent.py | يجلب 24 رمزاً: quotes, indicators, MTF, ICT, vol, calendar |
| sentiment | sentiment_agent.py | FinBERT أو keywords |
| analysis | agentic_brain.py | Claude + 17 أداة (12 iteration max). Fallback: analysis_agent ensemble |
| risk | risk_agent.py | compute_safe_sizing + FN guards |
| supervisor | supervisor_agent.py | قرار نهائي واحد |
| execution | execution_agent.py | MT5 live أو Paper |

---

## أدوات الدماغ (17+)

**registry.py + agentic_brain.py**

1. `get_adaptive_policy()` — سياسة دفاعية APE
2. `universe_snapshot()` — مسح 24 رمز
3. تحليل عميق (1–3 رموز): indicators, MTF, ICT, Wyckoff, Elliott, Harmonic, Volume Profile, Chart Patterns, Volatility, Sentiment, Calendar, Correlation, Quote
4. `query_history()` — قرارات وصفقات سابقة
5. `get_prop_status()` — FundedNext compliance
6. `apply_adaptive_change()` — تقليل مخاطر، إيقاف رمز، SKIP_SESSION (دفاعي فقط)
7. `run_python_code()` — sandbox numpy/pandas (5s timeout) — **راجع أمانه**

**قاعدة:** الأدوات read-only. الدماغ يقترح — risk + execution يفوّضان.

---

## FundedNext Stellar 2-Step (مدمج + توضيحات)

| | يومي | كلي |
|--|------|-----|
| داخلي (يتوقف قبل FN) | 4% | 9% |
| FN hard cap (رسمي) | 5% | 10% |

**مؤكد رسمياً (FN):** 5% daily loss، 10% maximum loss؛ HFT **غير مسموح**؛ EAs/استراتيجيات مسموحة مع **اتساق** خلال التحدي؛ حد أدنى **5 أيام تداول** و**5 صفقات** — **لا حد أقصى رسمي** لعدد الصفقات.

**قواعد داخلية (ليست كلها قواعد FN مكتوبة):**
- SL إلزامي على كل أمر
- **min hold 60s** — internal anti-HFT safety rule (unless FundedNext confirms otherwise in writing). FN تمنع HFT؛ هذا حد محافظ داخلي.
- **max 20 trades/day** — internal safety cap only (NOT an official FN max)
- max 5 مراكز متزامنة (داخلي)
- min conviction 0.60 (داخلي)
- max risk per trade 0.8% (داخلي)
- blackout أخبار HIGH ±10 دقائق (داخلي محافظ)
- XAUUSD leverage 1:10 (FN Jan 2026)

---

## محذوف عمداً (لا تقترح إعادته)

- **execution_variance** — jitter lots/pips، entry delay عشوائي، schedule jitter، skip-signal %، نوافذ lunch/sleep وهمية
- **anti_detection** — تمويه بشري

**ملاحظة:** APE ≠ execution_variance. APE موجود ومسموح (دفاعي).

---

## تناقضات/نقاط للمراجعة

1. data_agent يجلب **24 رمزاً كل دورة** — الدماغ يحلّل 1–3 فقط (تكلفة Twelve Data)
2. إذا الدماغ HOLD للكل → fallback ensemble قد ي contradict الحذر
3. دماغ Claude + مشرف GPT-4o-mini — قد يختلفان
4. prompt يذكر 0.55، config = 0.60
5. لم يُختبر backtest حقيقي بعد
6. **`run_python_code` sandbox** — هل آمن في ACTIVE mode؟
7. **APE reset** (RESET_RISK, RESUME_SYMBOL, RESET_CONVICTION) — هل شروط التعافي كافية؟

---

## الرموز (24)

Forex 19 + XAUUSD, XAGUSD + US30, US500, USTEC

---

## المطلوب منك — أجب بالعربية بهذا الشكل:

### 1) ملخص (5 نقاط)
### 2) نقاط القوة (ما نبقيه)
### 3) مخاطر/عيوب (high / medium / low)
### 4) أفضل 5 تحسينات عملية (تعديلات صغيرة، ليس إعادة كتابة كاملة)
### 5) إجابات على هذه الأسئلة:

**Architecture**
1. هل ترتيب LangGraph optimal؟
2. هل emergency → skip كافٍ لعطلة نهاية الأسبوع؟

**Agentic Brain**
3. هل 17 أداة كثيرة؟ ماذا ندمج أو نحذف؟
4. هل 12 iteration مناسب للتكلفة؟
5. هل نزيل ensemble fallback عند HOLD المتعمد؟

**Risk**
6. هل compute_safe_sizing محافظ enough لـ FN Phase 1؟
7. فجوات في prop_rules vs FN 2026 الرسمية؟

**Security (مهم)**
8. راجع `run_python_code` / `sandbox.py`: هل يجب تعطيله في ACTIVE mode؟ هل sandbox كافٍ؟ هل يمكن قراءة ملفات أو imports خطرة أو استهلاك CPU؟

**APE**
9. راجع APE reset logic (RESET_RISK, RESUME_SYMBOL, RESET_CONVICTION): هل شروط التعافي كافية؟ هل LLM يمكنه فك القيود بسرعة بعد خسائر؟

**Efficiency**
10. كيف نقلل Twelve Data calls؟
11. هل ن prefetch top-N رموز في الكود؟

**Operations**
12. أولوية: Tunnel، auto-start، backtest، إزالة fallback؟

---

**قيود:**
- لا anti-detection / لا execution variance (jitter/delay/randomization)
- APE الدفاعي مسموح — لا تحذفه
- EA معلن لـ FN
- تعديلات صغيرة في Cursor
- لا تكسر VPS الشغّال

**تنبيه:** لا تعتبر إجابتك توصية مالية أو ضمان ربح. المطلوب **مراجعة تقنية/تشغيلية/أمنية فقط** — ليس «هل سيربح الروبوت؟».

---

▲ **انتهى النص — انسخ حتى هنا**
