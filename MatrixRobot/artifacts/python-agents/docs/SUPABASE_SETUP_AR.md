# Supabase + PostgreSQL + pgvector — إعداد Matrix Robot

## 1) إنشاء مشروع Supabase (مجاني)

1. افتح https://supabase.com وسجّل دخول
2. **New Project** → اسم: `matrix-robot`
3. اختر كلمة سر للقاعدة — **احفظها**
4. انتظر ~2 دقيقة حتى يجهز المشروع

## 2) تفعيل pgvector

في Supabase: **SQL Editor** → New query → الصق:

```sql
CREATE EXTENSION IF NOT EXISTS vector;
```

→ **Run**

> Brain يُنشئ الجداول تلقائياً عند التشغيل — لا حاجة لSQL إضافي.

## 3) نسخ DATABASE_URL

1. **Project Settings** → **Database**
2. **Connection string** → **URI**
3. انسخ الرابط — يبدأ بـ:
   `postgresql://postgres.[ref]:[PASSWORD]@...pooler.supabase.com:6543/postgres`
4. استبدل `[PASSWORD]` بكلمة سر القاعدة

## 4) إضافة إلى `.env` على VPS

```env
DATABASE_URL=postgresql://postgres.xxxx:YOUR_PASSWORD@aws-0-eu-central-1.pooler.supabase.com:6543/postgres
```

## 5) Telegram (اختياري — موصى به)

1. في Telegram: افتح [@BotFather](https://t.me/BotFather)
2. `/newbot` → اسم → username
3. انسخ **Token**
4. افتح محادثة مع البot → `/start`
5. للحصول على Chat ID — شغّل Brain ثم:
   ```powershell
   # أو استخدم @userinfobot
   ```
6. في `.env`:
```env
TELEGRAM_BOT_TOKEN=123456:ABC...
TELEGRAM_CHAT_ID=your_chat_id
```

## 6) الحساب الحقيقي ForexIraq

في `.env` — `ACCOUNTS_JSON` (سطر واحد):

```env
ACCOUNTS_JSON=[{"id":"forexiraq_real","label":"ForexIraq Real","bridge_url":"http://127.0.0.1:5556","account_profile":"REAL","enabled":false,"starting_balance":78,"risk_per_trade_pct":2.5,"max_daily_drawdown_pct":8.0,"max_total_drawdown_pct":15.0,"max_concurrent_positions":5,"max_trades_per_day":40,"min_conviction_threshold":0.55,"symbols":""}]
```

- `symbols: ""` = **كل الرموز** (25 زوج/معدن/مؤشر من Brain)
- **5** صفقات مفتوحة كحد أقصى
- **40** صفقة/يوم

## 7) التحقق بعد restart Brain

```powershell
Invoke-RestMethod http://127.0.0.1:8000/agents/memory/status
Invoke-RestMethod http://127.0.0.1:8000/agents/scheduler/status
Invoke-RestMethod http://127.0.0.1:8000/agents/news/status
```

## 8) الجدولة 90 دقيقة

Brain يبدأ Scheduler تلقائياً كل **90 دقيقة** (إلا إذا كان محفوظاً بقيمة أخرى).

لتغيير يدوياً:
```powershell
Invoke-RestMethod -Method POST http://127.0.0.1:8000/agents/scheduler/start `
  -ContentType "application/json" -Body '{"interval_minutes": 90}'
```

## التكلفة

| الخدمة | السعر |
|--------|-------|
| Supabase Free | $0 |
| pgvector | $0 |
| Embeddings (OpenRouter) | ~$0.0001/دورة |
| Telegram | $0 |
