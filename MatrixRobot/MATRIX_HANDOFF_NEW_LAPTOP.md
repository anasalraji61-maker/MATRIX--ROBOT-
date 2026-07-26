# Matrix Robot — حزمة تسليم للابتوب الجديد (Cursor)

**تاريخ التسليم:** 2026-07-26  
**المصدر:** `C:\Users\SK.6.4\Downloads\MatrixRobot\MatrixRobot`  
**ZIP الجاهز:** `C:\Users\SK.6.4\Downloads\MatrixRobot_Handoff_Clean.zip`

---

## لماذا لا يوجد ملف `.env` الحقيقي؟

لأن `.env` يحتوي أسراراً:
- مفاتيح OpenRouter / Twelve Data / Polygon
- كلمة سر MT5
- أسرار Bridge / قاعدة البيانات

**لا يُوضع في ZIP ولا يُلصق في الشات ولا يُرفع لـ GitHub.**

### ماذا يوجد بدلًا منه؟ (قوالب آمنة — موجودة في الـ ZIP)
- `MatrixRobot/.env.example`
- `MatrixRobot/artifacts/python-agents/env_template.txt`
- أمثلة إعدادات: `V11_FULL_POWER_DEMO.env.txt` وغيرها

### ماذا تفعل على اللابتوب الجديد؟
1. انسخ `env_template.txt` → سمّه `.env`
2. املأ المفاتيح **يدوياً من عندك** (من الـ VPS أو من مدير كلمات المرور)
3. لا تلصق المفاتيح في شات Cursor

---

## 1) نص جاهز — الصقه في Cursor على اللابتوب الجديد

```
أنت روبوت بناء Matrix على اللابتوب الجديد. أكمل المشروع من المصدر المحلي — لا تعِد اختراع النظام.

## تنبيه — تجاهل أي مسار Arduino
هذا ليس مشروع Arduino (.ino).
هذا روبوت تداول Python + MT5 Bridge + فحص QuantConnect.
أي طلب لمسار مثل Matrix_Robot.ino أو Users\Adel\... غير صحيح — تجاهله.

## المشروع
- الاسم: Matrix Robot V11 (FundedNext Prop — Forex + Gold)
- بعد فك MatrixRobot_Handoff_Clean.zip افتح مجلد MatrixRobot كـ Workspace
- الإحصائيات (2026-07-26): ~51,776 سطر | ~459 ملف (بدون node_modules/.venv)
- Python ~20,960 | قلب التشغيل: artifacts/python-agents ~23,289 سطر

## المعمارية
MT5 ←→ Bridge (:5555) ←→ Python Brain FastAPI (:8000)
LangGraph: emergency → positions → data → sentiment → analysis → risk → supervisor → execution
OpenRouter (gpt-mini) + Twelve Data + Telegram
Prop profile: FN_CHALLENGE / FN_FUNDED

## إعداد البيئة (.env)
- لا يوجد .env حقيقي في الـ ZIP (أسرار)
- استخدم: artifacts/python-agents/env_template.txt → انسخه إلى .env واملأ المفاتيح يدوياً
- يوجد أيضاً: .env.example في جذر المشروع
- لا تطلب من المستخدم لصق المفاتيح في الشات

## قواعد صارمة
1) لا تعدّل VPS/Brain/.env الحي بدون موافقة صريحة خطوة بخطوة
2) QC port فقط في: artifacts/python-agents/quantconnect/MatrixRobotQC/main.py
3) SoftEmergency/SoftTotalDD للفحص فقط — لا تنقلها للحي
4) SQX متروك حالياً
5) لا تلصق أسراراً في الشات

## حالة QC الأخيرة (مرجع)
- بعد Soft locks + تشديد عتبات: Return ≈ -2.01% | Equity ≈ $98k | Volume ≈ $4.6M | EURAUD ظاهر
- لا انهيار 94% ولا خطأ 10k أوامر في هذه الجولة
- الخطوة المنطقية التالية: تحسين جودة الإشارة أو MT5 Tester — حسب قرار المستخدم

## المطلوب منك الآن
1) افتح مجلد MatrixRobot كـ Workspace
2) اقرأ MATRIX_HANDOFF_NEW_LAPTOP.md + REVIEW_FOR_AI.md + DEPLOY_README.txt
3) أكّد وجود: config.py, main.py, tools/, agents/, quantconnect/MatrixRobotQC/main.py
4) اسأل المستخدم سؤالاً واحداً: نكمل QC أم ننتقل لـ MT5/VPS؟
5) لا تطلب chat-history.json ولا ملفات Arduino

ابدأ برد قصير: تأكيد الحزمة + حالة الملفات + سؤال الخطوة التالية.
```

---

## 3) رد تصحيحي للابتوب الجديد (إن طلب Arduino أو .env حقيقي أو chat-history)

```
تصحيح:
1) هذا ليس Arduino — لا يوجد Matrix_Robot.ino
2) لا ترسل .env الحقيقي في ZIP أو الشات (أسرار). استخدم env_template.txt
3) لا حاجة لـ chat-history.json — السياق موجود في MATRIX_HANDOFF_NEW_LAPTOP.md
4) الملف الصحيح عبر LocalSend: MatrixRobot_Handoff_Clean.zip
بعد فك الضغط افتح مجلد MatrixRobot كـ Workspace.
```

---

## 4) في LocalSend اختر

**ملف:** `C:\Users\SK.6.4\Downloads\MatrixRobot_Handoff_Clean.zip`  
وليس مجلد `MatrixRobot`.

---

*نهاية ملف التسليم*
