# V11 Trading Council — خطة فقط (لا تطبيق قبل تقرير V10)

**الحالة:** PLANNING — ممنوع التطبيق حتى مراجعة `REPORT_2DAYS.md` من VPS  
**الأساس:** V10 hotfix v3 يعمل على Demo — يجمع البيانات  
**الهدف:** تقوية القرار بدون 7 LLMs مكلفة  

---

## 1) لماذا ننتظر؟

قبل V11 نحتاج من `daily_report` + Postgres:

| السؤال | لماذا |
|--------|--------|
| دورات full vs scanner vs maintenance | هل Smart Watcher يقلل الفرص؟ |
| HOLD ÷ cycles | هل النظام مخنوق أم انتقائي؟ |
| risk vs supervisor rejections | أين يُرفض؟ |
| candidates → LLM escalations | تكلفة vs فرص |
| win/loss per trade | جودة أم حظ؟ |

**لا خفض عتبات. لا V11 كود. حتى يصل التقرير.**

---

## 2) ما يغطيه V10 اليوم (~65–70% من المخطط)

| خطوة المخطط | V10 |
|-------------|-----|
| استقبال بيانات | ✅ data_agent |
| فلتر سلامة | ✅ emergency + quarantine |
| Smart Watcher | ✅ cycle_planner |
| تحليل تقني / ICT | ✅ ensemble + brain |
| أخبار / sentiment | ✅ sentiment_agent |
| Risk veto | ✅ risk_batch |
| Meta Judge | 🟡 supervisor (بسيط) |
| Skeptic Brain | ❌ |
| Council scores -1/+1 | ❌ |
| Post-Trade Learning | 🟡 ML/RL shadow فقط |
| Strategy Router | ❌ |

---

## 3) V11 — أولويات التنفيذ (بعد التقرير)

### المرحلة A — أعلى عائد / أقل مخاطرة
1. **Skeptic Brain** — قواعد + GPT-4o-mini فقط عند candidate قوي  
   - أسئلة: spread؟ خبر؟ دخول متأخر؟ revenge trade؟  
   - **Veto** — يوقف الصفقة حتى لو باقي العقول موافقة  

2. **Post-Trade Attribution** — بعد كل إغلاق  
   - سجل: سبب الدخول، الجلسة، الاستراتيجية، سبب الخسارة/الربح  
   - يغذي ML/RL لاحقاً (لا enforce فوراً)  

### المرحلة B
3. **Regime Brain** — trend / range / high vol (قواعد، بدون LLM)  
4. **Strategy Router** — اختيار استراتيجية حسب regime  

### المرحلة C
5. **Council scores** — كل عقل يعطي -1..+1  
6. **Meta Judge v2** — أوزان حسب regime → NO TRADE / WATCH / MICRO / SMALL / NORMAL  

---

## 4) قواعد التكلفة (ثابتة)

| الطبقة | LLM؟ |
|--------|------|
| Scanner | ❌ |
| Technical / Regime / Strategy | ❌ |
| Risk / Prop | ❌ |
| News briefing | mini (موجود) |
| Skeptic | mini عند escalation فقط |
| Meta Judge | mini عند candidate قوي |
| Daily review | مرة/يوم اختياري |

**لا 7 نماذج كاملة في كل دورة.**

---

## 5) قرارات مؤجلة (حتى التقرير)

| القرار | الحالة |
|--------|--------|
| خفض `NORMAL_TRADE_MIN_STRENGTH` | ⏸ مؤجل |
| رفع الرموز من 25 → 55 | ⏸ مؤجل — حسب التكلفة والتقرير |
| تفعيل ML/RL enforce | ⏸ مؤجل |
| V11 كود | ⏸ مؤجل |

---

## 6) معايير الانتقال V10 → V11

| الشرط | الهدف |
|--------|--------|
| ≥ 20 دورة full مسجّلة | عينة كافية |
| فهم top-3 أسباب HOLD | نعرف أين نصلح |
| ≥ 10 صفقات مغلقة (ديمو) | post-trade معنى |
| ChatGPT + Cursor يتفقان على السبب | لا تطوير عشوائي |

---

## 7) أمر التقرير (VPS)

```powershell
cd C:\MatrixRobot\MatrixRobot\MatrixRobot\artifacts\python-agents
$env:PYTHONPATH="."
.\.venv\Scripts\python.exe -m tools.daily_report --days 2 -o REPORT_2DAYS.md
```

أرسل `REPORT_2DAYS.md` لـ ChatGPT و Cursor.

---

*وثيقة تخطيط — لا تمثل كوداً منفّذاً.*
