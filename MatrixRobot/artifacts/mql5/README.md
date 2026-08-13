# MatrixGuard — طبقة حماية MQL5 (ليست روبوت تداول)

## ماذا يفعل؟
- يراقب نبض **Bridge** على `http://127.0.0.1:5555/version`
- يراقب **Daily DD** و **Total DD** من حساب MT5 مباشرة
- عند الخطر: تنبيه، واختيارياً إغلاق كل المراكز
- **لا يفتح صفقات** — العقل يبقى في Python Brain + Bridge

## طريقة Cursor + MetaEditor (مقترح جيميناي — معدّل)

### 1) انسخ الملف إلى MT5
شغّل من جذر المشروع:
```bat
artifacts\mql5\install-to-mt5.bat
```
أو انسخ يدوياً:
`artifacts\mql5\Experts\MatrixGuard.mq5`
→ مجلد:
`...\MetaQuotes\Terminal\<ID>\MQL5\Experts\`

### 2) افتح نفس المجلد في Cursor (اختياري)
File → Open Folder → مجلد `MQL5` الخاص بـ MT5  
عدّل `Experts\MatrixGuard.mq5` واحفظ (Ctrl+S)

### 3) Compile في MetaEditor
- افتح `MatrixGuard.mq5` في MetaEditor
- اضغط **F7**
- يجب أن يظهر `MatrixGuard.ex5` بدون أخطاء

### 4) إعداد MT5 المهم
Tools → Options → Expert Advisors:
- ☑ Allow algorithmic trading
- ☑ Allow WebRequest for listed URL  
  أضف: `http://127.0.0.1:5555`

### 5) شغّل على شارت
اسحب `MatrixGuard` إلى أي شارت → Allow Algo Trading  
اترك Brain/Bridge يعملان كالمعتاد.

## إعدادات مقترحة (Demo FundedNext-like)
| Input | قيمة |
|--------|------|
| InpMaxDailyDDPercent | 4.0 |
| InpMaxTotalDDPercent | 9.0 |
| InpCloseOnDailyDD | true |
| InpCloseOnTotalDD | true |
| InpCloseOnBridgeDown | false (تنبيه فقط أولاً) |

## ملاحظة أمان
`InpCloseOnBridgeDown=true` يغلق كل الصفقات إذا مات Bridge. ابدأ بـ `false` حتى تتأكد أن WebRequest يعمل.
