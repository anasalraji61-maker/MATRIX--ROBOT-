# V11 Full Power Demo — Cursor Implementation Spec

> **انسخ هذا الملف كاملًا إلى Cursor.** الهدف: نسخة Demo نشطة — 55 رمزًا، 24/5، Scalping + Council. **التكلفة غير مهمة الآن.** **لا تكسر أنظمة الحماية.**

---

## الهدف في جملة واحدة

بناء `TRADING_MODE_PROFILE=FULL_POWER_DEMO`: روبوت يحلل **55 رمزًا كاملة**، يعمل **24/5**، يفتح صفقات أكثر في الديمو عبر **Scalping Engine مستقل** + **Trading Council**، مع بقاء **كل** حماية V10 (risk, DD, SL/TP, emergency, data quality).

---

## قواعد لا تُخالف

### ممنوع تعطيل أو تجاوز
- emergency guard
- drawdown guard (daily + total)
- data quality gate / per-symbol quarantine
- SL/TP verification بعد الفتح
- broker symbol validation
- `manual_check_required` / bridge circuit
- max daily loss / max total loss / max open risk
- martingale / averaging down

### Demo-only (افتراضي)
- إذا `mt5_server` لا يحتوي `demo` → فرض تلقائي:
  - `SCALPING_ENABLED=false`
  - `COUNCIL_MODE=shadow` أو `advisory`
  - `FULL_POWER_DEMO=false`
- `I_UNDERSTAND_REAL_RISK=true` مطلوب صراحةً لتفعيل FULL_POWER على real/funded (افتراضي: ممنوع)

### لا تكسر V10
- **لا** تخفّض عتبات V10 swing/intraday عشوائيًا
- أضف طبقات جديدة: Scalping + Council + Full Universe
- `TRADING_PROFILE=aggressive` **ليس** البديل — استخدم `FULL_POWER_DEMO`

---

## Phase 0 — Config & Profile (ابدأ هنا)

### إعدادات جديدة في `config.py`

```env
# ── Full Power Demo profile ──
TRADING_MODE_PROFILE=FULL_POWER_DEMO

SYMBOL_UNIVERSE_MODE=full_55
SYMBOLS=                    # يُملأ تلقائيًا من DEFAULT_SYMBOLS_CSV (~55)
RUN_24H_FULL_ANALYSIS=true
FULL_ANALYSIS_ALL_SYMBOLS=true
DEEP_ANALYSIS_TOP_N=15
COUNCIL_TOP_N=8
COUNCIL_FULL_UNIVERSE_DEBUG=false

# 24h — لا نوم خارج الجلسات
SESSION_FILTER_MODE=extended
SMART_WATCHER_ENABLED=true
SMART_WATCHER_EXECUTE_OFF_SESSION_SMALL=true
PHASE5_SESSION_REQUIRE_KILLZONE=false

# دورات أسرع في FULL_POWER (التكلفة غير مهمة)
SCHEDULER_INTERVAL_MINUTES=10
PHASE5_SCHEDULER_HIGH_LIQ_MINUTES=10
PHASE5_SCHEDULER_MEDIUM_LIQ_MINUTES=12
PHASE5_SCHEDULER_LOW_LIQ_MINUTES=15

# V10 limits — أكثر نشاطًا في الديمو فقط
MAX_TRADES_PER_DAY=30
MAX_CONCURRENT_POSITIONS=7
INTRADAY_MAX_TRADES_PER_DAY=10
SWING_MAX_TRADES_PER_DAY=3

# Scalping (مستقل)
SCALPING_ENABLED=true
SCALPING_DEMO_ONLY=true
SCALPING_MODE=enforce
SCALPING_ALLOWED_ASSETS=FX_ONLY
SCALPING_TIMEFRAMES=M1,M5,M15
SCALPING_MAX_TRADES_PER_DAY=15
SCALPING_MAX_OPEN_TRADES=2
SCALPING_RISK_MULTIPLIER=0.08
SCALPING_MIN_STRENGTH=0.58
SCALPING_MIN_RR=1.05
SCALPING_MAX_HOLD_MINUTES=30
SCALPING_USE_TRAILING=true
SCALPING_USE_BREAKEVEN=true

# Council
COUNCIL_ENABLED=true
COUNCIL_MODE=shadow
COUNCIL_GPT_TOP_N=8

# Correlation أقوى
MAX_SAME_CURRENCY_EXPOSURE=3
MAX_CORRELATED_TRADES=2

# Indices تبقى معطلة حتى إثبات MT5
ACTIVE_DISABLED_SYMBOLS=US30,US500,USTEC
```

### ملف `tools/trading_mode_profiles.py`
- `apply_trading_mode_profile(settings)` يُستدعى من `config.model_post_init`
- عند `FULL_POWER_DEMO`: يطبّق كل الإعدادات أعلاه + 55 رمزًا + 24h
- عند `conservative` / فارغ: سلوك V10 الحالي بدون تغيير

### `/agents/health` — أضف
```json
{
  "configured_symbols_count": 55,
  "active_symbols_count": 52,
  "disabled_symbols": ["US30","US500","USTEC"],
  "asset_class_counts": {"fx": 48, "metals": 2, "oil": 2, "indices": 0},
  "trading_mode_profile": "FULL_POWER_DEMO"
}
```

---

## Phase 1 — 55-Symbol Full Data Pipeline

### المطلوب
كل دورة **full** تجلب بيانات **كل** الرموز الـ 55 (ليس 25 فقط):

| خطوة | الملف | التغيير |
|------|-------|---------|
| Quotes لكل الرموز | `agents/data_agent.py` | `symbol_list` = universe كامل |
| Bars H1 لكل الرموز | `agents/data_agent.py` | parallel fetch، لا `mtf_max_symbols` cap في FULL_POWER |
| Indicators لكل رمز | `tools/indicators.py` | بدون تغيير — يُحسب لكل bar set |
| MTF لأفضل 15 | `tools/multi_timeframe.py` | deep فقط لـ `DEEP_ANALYSIS_TOP_N` |
| ICT basic لكل 55 | `agents/data_agent.py` | lightweight ICT على H1 للكل |

### Funnel (للتنظيم فقط — ليس لتوفير تكلفة)
```
55 symbols → data + indicators + basic ICT + preliminary_score
    ↓
top 15 → deep MTF + volatility regime + correlation pre-check
    ↓
top 8 → Trading Council كامل
    ↓
risk engine → execution
```

### `COUNCIL_FULL_UNIVERSE_DEBUG=true`
- يشغّل council على كل 55 (اختبار فقط — ثقيل)

### ملفات جديدة/محدّثة
- `tools/universe_manager.py` — universe، disabled، asset counts
- `tools/preliminary_scorer.py` — score سريع لكل 55 قبل deep

---

## Phase 2 — 24/5 Cycle Planner

### المطلوب في `tools/cycle_planner.py`
عند `RUN_24H_FULL_ANALYSIS=true` + `FULL_POWER_DEMO`:

| الوقت | cycle_type | ملاحظة |
|-------|------------|--------|
| London/NY | `full` | intraday + scalping + council |
| Asian | `full` | scalping/range + small |
| خارج الجلسات | `full` (ليس scanner فقط) | small/micro فقط، max 1-2 open |

**لا** maintenance/scanner-only خارج الجلسات في FULL_POWER — استخدم `full` مع قيود off-session في risk.

### off-session limits (`tools/off_session_limits.py`)
- tier: MICRO/SMALL فقط
- `off_session_max_open_trades=2`
- require: spread ok, no high-impact news, data clean

---

## Phase 3 — Scalping Engine (مستقل — موجود جزئيًا، أكمله)

### الملفات (بناء على V11 الحالي)
- `tools/scalp_engine.py` ✅ موجود — وسّعه
- `tools/scalp_strategies.py` ✅ — أضف حقول JSON كاملة لكل إشارة
- `tools/scalp_scanner.py` — M1/M5/M15 fetch لكل FX في universe أو top candidates
- `tools/scalp_risk.py` — SL/TP صغير، max hold 30min، trailing/breakeven
- `tools/scalp_position_manager.py` — إغلاق بعد 30min، BE @ 0.5R، trail

### كل إشارة سكالبينج ترجع
```json
{
  "strategy_name": "ema_pullback_scalp",
  "direction": "BUY",
  "strength": 0.72,
  "confidence": 0.68,
  "entry_reason": "...",
  "invalidation_reason": "...",
  "sl_pips": 5,
  "tp_pips": 7,
  "expected_hold_minutes": 15,
  "spread_cost_warning": false
}
```

### الاستراتيجيات (6)
1. EMA Pullback Scalp
2. Micro Breakout
3. Liquidity Sweep Reversal
4. Asian Range Mean Reversion
5. Momentum Continuation M5
6. Volatility Expansion Scalp

### rollout
```
ساعات 0-3:  SCALPING_MODE=shadow
ساعات 3-9:  SCALPING_MODE=advisory
بعدها:      SCALPING_MODE=enforce (demo only)
```

---

## Phase 4 — Trading Council (7 عقول + Meta Judge)

### ملف `tools/council/` أو توسيع `tools/trading_council.py`

| Brain | نوع | وظيفة |
|-------|-----|--------|
| Market Regime | rules | trend/range/vol/news/liquidity |
| Technical Quant | rules | EMA/RSI/MACD/ADX/ATR/BB/Ichimoku/Pivot/SR/MTF |
| ICT / Price Action | rules | BOS/CHoCH/FVG/OB/sweep/premium-discount |
| Scalping | rules | spread/vol/M1-M5 structure/quick RR/hold time |
| News & Macro | rules + calendar | high impact, USD/gold/oil, sentiment |
| Strategy Router | rules | scalp/intraday/swing/no_trade |
| Skeptic | rules | late entry, spread eats TP, news, fake signal, correlation |
| Risk & Prop | rules | lot/DD/open risk/positions/SL valid — **veto نهائي** |
| Meta Judge | rules | يجمع كل شيء → قرار نهائي |

### JSON موحد لكل عقل
```json
{
  "brain": "technical_quant",
  "symbol": "EURUSD",
  "signal": "buy",
  "score": 0.65,
  "confidence": 0.70,
  "suggested_strategy": "scalp",
  "suggested_tier": "small",
  "veto": false,
  "veto_reason": "",
  "short_reason": "MTF bullish, RSI pullback",
  "risk_notes": []
}
```

### Meta Judge output
```json
{
  "symbol": "EURUSD",
  "final_action": "BUY",
  "trade_style": "SCALP",
  "tier": "SMALL",
  "confidence": 0.72,
  "selected_strategy": "ema_pullback_scalp",
  "entry_reason": "...",
  "rejection_reason": "",
  "vetoes": [],
  "approved_by": ["technical_quant","scalping"],
  "rejected_by": [],
  "recommended_sl": 1.08450,
  "recommended_tp": 1.08520,
  "expected_hold_minutes": 15
}
```

### GPT
- استخدم GPT-4o-mini **فقط** لأفضل 8 بعد rules (اختياري — التكلفة غير مهمة لكن rules أولاً)
- `COUNCIL_MODE=shadow|advisory|enforce` مثل scalping

---

## Phase 5 — Correlation & Currency Exposure

### ملف `tools/currency_exposure.py`
- احسب exposure: USD, EUR, GBP, JPY, CHF, AUD, NZD, CAD, XAU, XAG, OIL
- منع: >3 صفقات بنفس العملة، >2 correlated بنفس الاتجاه
- تقرير في cycle result:
  - `exposure_by_currency`
  - `correlated_positions`
  - `blocked_by_correlation`

---

## Phase 6 — Endpoints & Reports

### Endpoints جديدة/محدّثة
| Endpoint | يعرض |
|----------|------|
| `GET /agents/scalping/status` | candidates, approved, shadow, trades by strategy |
| `GET /agents/council/status` | brain scores, meta decisions, vetoes |
| `GET /agents/universe/status` | 55 symbols, disabled, asset classes, data coverage |
| `GET /agents/strategy/status` | router mode, active strategies, win/loss by strategy |

### حقول تقرير كل دورة
- `scanned_symbols_count` (يجب ≈ 55)
- `deep_analysis_count` (≈ 15)
- `council_evaluated_count` (≈ 8)
- `top_candidates` (10)
- `scalping_candidates`, `scalping_approved`, `rejected_reasons`, `veto_reasons`
- `trades_opened_by_strategy`, `average_hold_minutes`
- `spread_cost_estimate`, `execution_latency_ms`

### Telegram (مختصر)
- كل صفقة منفذة ✅
- كل veto مهم ⚠️
- ملخص كل 3 ساعات 📊
- تقرير نهاية اليوم 📋

### `tools/daily_report.py`
- أضف أقسام: scalping stats, council stats, exposure, strategy breakdown

---

## Phase 7 — Tests (قبل قول "جاهز")

```bash
python -m compileall -q .
PYTHONPATH=. pytest -q
```

### اختبارات إلزامية جديدة `tests/test_v11_full_power.py`
- [ ] `get_settings()` + `FULL_POWER_DEMO` profile loads
- [ ] 55 symbols in universe (`configured_symbols_count >= 52`)
- [ ] asset classes classified correctly
- [ ] council JSON schema valid (pydantic models)
- [ ] scalping scanner on sample M5 data
- [ ] demo-only guard blocks non-demo server
- [ ] correlation blocker: 4 USD-long → blocks 5th
- [ ] risk veto cannot bypass skeptic+risk double veto
- [ ] SL/TP verification still runs in ACTIVE
- [ ] `daily_report` includes scalping/council fields
- [ ] FULL_POWER uses `full` cycle outside sessions (not scanner-only)

---

## ترتيب التنفيذ (لـ Cursor)

```
1. trading_mode_profiles.py + config + health endpoint
2. data_agent: fetch all 55 every full cycle
3. cycle_planner: 24h full cycles in FULL_POWER
4. Expand scalp engine + 6 strategies + position manager
5. Expand council: 8 brains + meta judge + pydantic schemas
6. currency_exposure + correlation hardening
7. endpoints: universe, strategy, expand scalping/council
8. telegram summaries + daily_report
9. tests + V11_FULL_POWER_DEMO.env.txt
10. Deploy zip + DEPLOY_V11_FULL_POWER_VPS.ps1
```

---

## ملف env جاهز للـ VPS Demo

احفظ كـ `.env` additions (دمج مع V10):

```env
TRADING_MODE_PROFILE=FULL_POWER_DEMO
RUN_24H_FULL_ANALYSIS=true
FULL_ANALYSIS_ALL_SYMBOLS=true
SYMBOL_UNIVERSE_MODE=full_55

SCALPING_ENABLED=true
SCALPING_DEMO_ONLY=true
SCALPING_MODE=shadow
COUNCIL_ENABLED=true
COUNCIL_MODE=shadow

SESSION_FILTER_MODE=extended
SMART_WATCHER_ENABLED=true
SMART_WATCHER_EXECUTE_OFF_SESSION_SMALL=true

SCHEDULER_INTERVAL_MINUTES=10
MAX_TRADES_PER_DAY=30
SCALPING_MAX_TRADES_PER_DAY=15

TRADING_PROFILE=conservative
ACTIVE_DISABLED_SYMBOLS=US30,US500,USTEC
```

**Rollout على VPS:**
1. نشر الكود
2. `SCALPING_MODE=shadow` + `COUNCIL_MODE=shadow` — 3 ساعات
3. `advisory` — 6 ساعات
4. `enforce` — إذا التقارير جيدة

---

## Definition of Done

- [ ] `/agents/health` يظهر `configured_symbols_count` ≈ 55
- [ ] كل full cycle يحلل 55 رمزًا (تحقق من cycle log)
- [ ] الروبوت يعمل 24/5 بدون scanner-only خارج الجلسات
- [ ] Scalping منفصل — صفقات SCALP tier لا تختلط مع intraday
- [ ] Council يُخرج meta decisions لأفضل 8
- [ ] Demo guard يمنع enforce على non-demo
- [ ] كل حماية V10 ما زالت تعمل
- [ ] pytest كامل أخضر
