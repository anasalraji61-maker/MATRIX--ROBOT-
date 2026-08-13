# Matrix Robot — Contabo Windows Server (تشغيل 24/7)

## المعمارية (قرارك: VPS فقط + PWA على الهاتف)

```
[Contabo Windows]  Python :8000  +  API :8080  +  MT5 + Bridge :5555
        ↑
[هاتفك]  PWA → https://رابط-الداشبورد  (مراقبة)
[هاتفك]  تطبيق MT5  (نفس حساب الديمو = نفس الصفقات)
```

اللابتوب **غير مطلوب** بعد اكتمال الإعداد على VPS.

---

## المفاتيح: جديد من المواقع — لا تنسخ من Replit

**لماذا:** مفتاح Twelve Data ظهر داخل ملف `.replit` في المستودع → أي شخص يرى GitHub قد يستخدمه.
**الإجراء:** أنشئ مفاتيح **جديدة** من المواقع، وألغِ/جدّد المفتاح القديم في لوحة Twelve Data.

| المتغير | من أين | ضروري؟ |
|---------|--------|--------|
| `TWELVE_DATA_API_KEY` | https://twelvedata.com | نعم (بيانات سوق حقيقية) |
| `OPENROUTER_API_KEY` | https://openrouter.ai | موصى به (دماغ LLM) |
| `SESSION_SECRET` | أنشئه أنت: `openssl rand -hex 32` أو PowerShell عشوائي | نعم |
| `MT5_LOGIN` / `MT5_PASSWORD` / `MT5_SERVER` | وسيط الديمو (نفس حسابك على الهاتف) | نعم لـ ACTIVE |
| `MT5_BRIDGE_SECRET` | سلسلة سرية طويلة (أنت تختارها) | نعم |
| `ALLOW_LIVE_TRADING` | `true` في `.env` | نعم لتفعيل ACTIVE |
| `TRADING_STATE` | `ACTIVE` | نعم (ديمو على VPS) |
| `POLYGON_API_KEY` | اختياري (مسار sentiment في Node) | لا |
| `OPENAI_API_KEY` | اختياري (احتياطي) | لا |

**لا تلصق المفاتيح في شات Cursor.** ضعها فقط في:
`C:\MatrixRobot\MatrixRobot\.env` على VPS.

---

## ACTIVE + حساب ديمو

1. ثبّت **MetaTrader 5** على نفس Windows Server.
2. سجّل دخول **حساب الديمو** (نفس بيانات الهاتف إن أردت مراقبة واحدة).
3. شغّل **MT5 Bridge** (`mt5_windows_bridge.py` على المنفذ 5555).
4. في `.env`:
   ```
   TRADING_STATE=ACTIVE
   ALLOW_LIVE_TRADING=true
   MT5_BRIDGE_URL=http://127.0.0.1:5555
   PYTHON_AGENT_URL=http://127.0.0.1:8000
   PORT=8080
   ```
5. أعد تشغيل Python بعد أي تغيير `.env`.

الهاتف: MT5 للمشاهدة فقط إن كان الروبوت ينفّذ على VPS (نفس الحساب).

---

## PWA على الهاتف

1. على VPS: `pnpm --filter @workspace/dashboard run build`
2. اعرض الواجهة عبر HTTPS (موصى به):
   - **Cloudflare Tunnel** (مجاني) → نطاق فرعي مثل `matrix.yourdomain.com`
   - أو فتح منفذ 443 مع شهادة (أصعب)
3. على الهاتف: Chrome → الرابط → **Add to Home Screen**.

`vite` مضبوط على `--host 0.0.0.0` للوصول من الشبكة.

---

## تثبيت سريع على VPS (PowerShell كمسؤول)

```powershell
# 1) أدوات (مرة واحدة)
winget install Git.Git OpenJS.NodeJS.LTS Python.Python.3.12
npm install -g pnpm

# 2) المشروع
git clone https://github.com/anasalraji61-maker/MATRIX--ROBOT-.git C:\MatrixRobot\MatrixRobot
cd C:\MatrixRobot\MatrixRobot
copy .env.example .env
# عدّل .env يدوياً (Notepad) — لا ترفع .env لـ GitHub

# 3) Python
cd artifacts\python-agents
py -3.12 -m venv .venv
.\.venv\Scripts\pip install -r requirements.txt
cd ..\..

# 4) Node
pnpm install
pnpm --filter @workspace/api-spec run codegen
pnpm --filter @workspace/dashboard run build
cd artifacts\api-server
node build.mjs
cd ..\..

# 5) تشغيل (استخدم scripts\start-contabo.ps1 بعد إنشاء .env)
```

---

## جدار ناري Windows

- افتح للعالم الخارجي فقط ما تحتاجه للمراقبة (مثلاً 443 عبر Tunnel).
- `8000` و `8080` و `5555`: يفضّل **localhost فقط** إن أمكن؛ الـ API يواجه الهاتف عبر نفس نفق HTTPS.

---

## خدمات تلقائية (بعد أول تشغيل ناجح)

استخدم `scripts\install-contabo-services.ps1` (NSSM) أو Task Scheduler لتشغيل:
1. MT5 Bridge
2. Python uvicorn
3. Node api-server
4. (اختياري) `vite preview` أو ملفات `dashboard/dist` خلف reverse proxy
