# Matrix Robot — دليل كامل لـ ChatGPT (V11 Full Power Demo)
> **تاريخ:** يونيو 2026 | **الحالة:** Hotfix v3 — جاهز للمراجعة (لا تنشر قبل pytest على VPS)

---

## Hotfix v3 (بعد مراجعة v2 zip)

| البند | v2 (ChatGPT) | v3 (بعد الإصلاح) |
|-------|--------------|------------------|
| pytest | 118 passed / **6 failed** | **129 passed** |
| `runtime_state.py` | مفقود من zip | ✅ مضمّن |
| `ml/rl/policy.py` | مفقود من zip | ✅ مضمّن |
| `SCALPING_MODE` | shadow | **enforce** (demo) |
| `COUNCIL_MODE` | shadow | **enforce** (demo) |
| Scalp execution | bypass بدون حماية | `scalp_execution_guard.py` — نفس بوابات V10 |
| correlation/exposure | جزئي | `scalp_risk` + `currency_exposure` |
| zip | `matrix_v11_full_power_v2.zip` | **`matrix_v11_full_power_v3.zip`** (~1MB, مُحدَّث) |
| حدود الصفقات | 7 مفتوحة / 30 يوم | **15 مفتوحة / 80 يوم** (+ سكالب 6/40) |

**ملاحظة:** الأسهم (stocks/CFDs) **غير مضافة** — الـ 55 رمز = Forex + Metals + Oil (+ indices معطلة).

---

## 1. أين الكود؟

| الموقع | المحتوى |
|--------|---------|
| **اللابتوب (Downloads)** | `C:\Users\SK.6.4\Downloads\MatrixRobot\MatrixRobot\artifacts\python-agents` |
| **VPS** | `C:\MatrixRobot\MatrixRobot\MatrixRobot\artifacts\python-agents` |
| **الاختبارات** | `129 passed` (hotfix v3) |

**ملاحظة:** أرسل ChatGPT الملفان التاليان من `Downloads`:
1. `matrix_v11_full_power_v3.zip` (~1MB) — الكود الكامل + tests + env
2. `CHATGPT_V11_COMPLETE_GUIDE.md` — هذا الدليل

تجاهل v1/v2 zip. داخل v3: `runtime_state.py`, `ml/`, `agents/`, `tools/`, `tests/` (347 ملف).

---

## 2. ما الذي بُني؟ (V11 — دفعة واحدة)

### الوضع الرئيسي
```
TRADING_MODE_PROFILE=FULL_POWER_DEMO
SESSION_FILTER_MODE=24h
RUN_24H_ALL_SYSTEMS=true
```

### ماذا يعني؟
- **55 رمزًا** تحليل كامل كل دورة
- **24/5** — لا نوم: scalping + intraday + swing + SMALL + NORMAL
- **مجلس العقول** (8 عقول + Meta Judge) في الـ pipeline
- **Scalping Engine** مستقل (لا يكسر V10)
- **Demo-only** — يُعطّل تلقائيًا على حساب غير demo

### Pipeline
```
emergency → position_manager → data (55) → sentiment → analysis (ensemble×55)
    → council (7+1 عقول) → risk → supervisor → execution
    → scalp_engine (منفصل بعد الدورة)
```

---

## 3. مجلس العقول (Matrix Trading Council)

| العقل | الوظيفة |
|-------|---------|
| Market Regime | trend/range/vol/news/liquidity |
| Technical Quant | RSI/MACD/ADX/EMA/BB/MTF |
| ICT Price Action | BOS/CHoCH/FVG/OB/sweep |
| Scalping Brain | spread/vol/M5/RR/hold time |
| News & Macro | calendar + sentiment |
| Strategy Router | scalp/intraday/swing |
| Skeptic | رفض: متأخر، spread، correlation |
| Risk & Prop | DD/lot/SL — veto نهائي |
| **Meta Judge** | WATCH/MICRO/SMALL/NORMAL → BUY/SELL/HOLD |

**ملف:** `tools/trading_council.py`  
**Schemas:** `models/council_schemas.py`  
**Agent:** `agents/council_agent.py`

---

## 4. Scalping Engine (مستقل)

- 6 استراتيجيات: EMA pullback, micro breakout, liquidity sweep, Asian range, momentum M5, vol expansion
- أوضاع: `SCALPING_MODE=shadow | advisory | enforce`
- FX فقط في البداية
- `tools/scalp_engine.py`, `scalp_strategies.py`, `scalp_risk.py`, `scalp_position_manager.py`

---

## 5. وضع 24 ساعة (كل الأنظمة)

| النظام | London/NY | Asian | Off-session |
|--------|-----------|-------|-------------|
| Scalping | ✅ | ✅ | ✅ |
| Intraday | ✅ | ✅ | ✅ |
| Swing | ✅ | ✅ | ✅ |
| SMALL trades | ✅ | ✅ | ✅ |
| NORMAL trades | ✅ | ✅ | ✅ |
| Full analysis 55 | ✅ | ✅ | ✅ |
| Council | ✅ | ✅ | ✅ |

**ملف:** `tools/session_24h.py`, `session_engine.py` (mode=24h)

خارج الجلسات: مخاطرة أقل تلقائيًا (NORMAL×0.35, SMALL×0.20)، حد 4 مفتوحة + 20/يوم off-session.

---

## 6. API Endpoints

| Endpoint | الغرض |
|----------|-------|
| `GET /agents/health` | symbols count, asset classes, profile |
| `GET /agents/council/status` | قرارات المجلس، vetoes |
| `GET /agents/scalping/status` | فرص السكالبينج |
| `GET /agents/universe/status` | 55 رمز + exposure |
| `GET /agents/strategy/status` | router + scores |
| `GET /agents/session/status` | 24h flags |

---

## 7. الإعدادات (.env) — انسخ للـ VPS Demo

```env
TRADING_MODE_PROFILE=FULL_POWER_DEMO
SESSION_FILTER_MODE=24h
RUN_24H_ALL_SYSTEMS=true
RUN_24H_FULL_ANALYSIS=true
FULL_ANALYSIS_ALL_SYMBOLS=true
SYMBOL_UNIVERSE_MODE=full_55

SCALPING_ENABLED=true
SCALPING_DEMO_ONLY=true
SCALPING_MODE=shadow
COUNCIL_ENABLED=true
COUNCIL_MODE=shadow

MAX_TRADES_PER_DAY=80
MAX_CONCURRENT_POSITIONS=15
SCALPING_MAX_TRADES_PER_DAY=40
SCALPING_MAX_OPEN_TRADES=6
SCHEDULER_INTERVAL_MINUTES=10

ACTIVE_DISABLED_SYMBOLS=US30,US500,USTEC
TRADING_PROFILE=conservative
```

**ملف جاهز:** `python-agents/V11_FULL_POWER_DEMO.env.txt`

---

## 8. Rollout المقترح (Demo)

| المرحلة | الإعداد | المدة |
|---------|---------|-------|
| 1 | `SCALPING_MODE=shadow` + `COUNCIL_MODE=shadow` | 3 ساعات |
| 2 | `advisory` | 6 ساعات |
| 3 | `enforce` (demo فقط) | إذا التقارير جيدة |

---

## 9. ما لم يُكسر (حماية V10)

- emergency guard
- drawdown daily/total
- data quality / quarantine
- SL/TP verification
- correlation + currency exposure
- manual_check_required
- لا martingale / لا averaging down

---

## 10. الملفات المرجعية في Downloads

| الملف | المحتوى |
|-------|---------|
| `CHATGPT_V11_COMPLETE_GUIDE.md` | **هذا الملف** — المرجع الشامل |
| `MatrixRobot/.../V11_FULL_POWER_CURSOR_SPEC.md` | مواصفات التطوير التفصيلية |
| `MatrixRobot/.../V11_FULL_POWER_DEMO.env.txt` | إعدادات env |
| `MatrixRobot/.../REPORT_FOR_CHATGPT.md` | تقرير قديم (قبل V11) |
| `MatrixRobot/.../V11_TRADING_COUNCIL_PLAN.md` | خطة قديمة (قبل Full Power) |

---

## 11. نشر على VPS

1. انسخ مجلد `python-agents` كامل من Downloads → VPS
2. دمج `V11_FULL_POWER_DEMO.env.txt` في `.env`
3. `pip install -r requirements.txt`
4. `PYTHONPATH=. pytest -q` (توقع **129 passed**)
5. أعد تشغيل خدمة Matrix Robot
6. تحقق: `/agents/health` → `active_symbols_count` ≈ 52

---

## 12. أسئلة لـ ChatGPT

1. هل rollout shadow→advisory→enforce منطقي لديمو MetaQuotes؟
2. هل عتبات `SCALPING_MIN_STRENGTH=0.58` مناسبة لجمع بيانات؟
3. هل 24h NORMAL خارج الجلسات آمن بمضاعف مخاطرة 0.35؟
4. متى نرفع `COUNCIL_MODE=enforce`؟
5. هل نحتاج تقرير `python -m tools.daily_report --days 2` قبل enforce؟

---

## 13. الفرق عن V10 على VPS (حاليًا)

| | V10 على VPS | V11 على اللابتوب |
|--|-------------|------------------|
| رموز | ~25 | 55 |
| جلسات | Smart Watcher | 24h full |
| Council | ❌ | ✅ 8 عقول |
| Scalping | ❌ | ✅ مستقل |
| دورات خارج الجلسة | scanner | full |

**V11 لم يُنشر بعد على VPS** — الكود على اللابتوب فقط حتى الآن.
