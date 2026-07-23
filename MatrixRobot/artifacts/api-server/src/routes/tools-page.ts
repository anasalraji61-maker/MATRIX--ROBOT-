import { Router, type IRouter } from "express";

const router: IRouter = Router();

type Row = { name: string; role: string };
type Section = { title: string; subtitle: string; color: string; rows: Row[] };

const SECTIONS: Section[] = [
  {
    title: "Platforms & Sites",
    subtitle: "المنصات والمواقع",
    color: "#38bdf8",
    rows: [
      { name: "Replit", role: "الاستضافة السحابية + بيئة التطوير" },
      { name: "FundedNext", role: "شركة الـ Prop Firm (التحدّي والتمويل)" },
      { name: "MetaTrader 5 (MT5)", role: "منصة التداول لدى البروكر" },
      { name: "MetaQuotes-Demo", role: "سيرفر الحساب التجريبي" },
      { name: "Twelve Data", role: "مزوّد أسعار الفوركس + الأخبار" },
      { name: "OpenRouter.ai", role: "بوابة الوصول لنماذج LLM" },
      { name: "Anthropic Claude 3.5", role: "النموذج الأساسي للقرارات" },
      { name: "OpenAI GPT-4o-mini", role: "النموذج الاحتياطي + تحليل الأخبار" },
      { name: "Cloudflare (cloudflared)", role: "رابط HTTPS عام للهاتف / الإنترنت" },
      { name: "ForexVPS", role: "الاستضافة الدائمة (MT5 + Dashboard + API + Brain)" },
      { name: "GitHub", role: "مستودع الكود وحفظ النسخ" },
      { name: "Tailscale Funnel", role: "بديل دائم لـ cloudflared (مجاناً)" },
    ],
  },
  {
    title: "Cloud Stack (Replit 24/7)",
    subtitle: "الجزء السحابي",
    color: "#60a5fa",
    rows: [
      { name: "React + Vite + Tailwind", role: "الواجهة الأمامية (Dashboard)" },
      { name: "shadcn/ui", role: "مكتبة العناصر الجاهزة" },
      { name: "PWA", role: "تطبيق على iPhone بدون App Store" },
      { name: "Express.js (Node)", role: "خادم API الوسيط" },
      { name: "TypeScript + Zod", role: "فحص أنواع البيانات" },
      { name: "OpenAPI + Orval", role: "توليد كود الاتصال تلقائياً" },
      { name: "FastAPI (Python)", role: "خدمة الذكاء الاصطناعي" },
      { name: "LangGraph", role: "تنسيق 6 وكلاء بالتسلسل" },
    ],
  },
  {
    title: "LangGraph Agents (×6)",
    subtitle: "الوكلاء الستة",
    color: "#fbbf24",
    rows: [
      { name: "Data Agent", role: "أسعار الفوركس والأخبار من Twelve Data" },
      { name: "Sentiment Agent", role: "تحليل مشاعر الأخبار عبر GPT" },
      { name: "Analysis Agent", role: "12 مؤشر فني (RSI, MACD, Ichimoku...)" },
      { name: "Risk Agent", role: "حساب الحجم (Kelly) + قواعد FundedNext" },
      { name: "Supervisor Agent", role: "القرار النهائي (LLM)" },
      { name: "Execution Agent", role: "فتح الصفقات على MT5" },
    ],
  },
  {
    title: "LLMs & Data Sources",
    subtitle: "الذكاء الاصطناعي والبيانات",
    color: "#c084fc",
    rows: [
      { name: "OpenRouter (Claude 3.5)", role: "المحلّل الأساسي للقرارات" },
      { name: "OpenAI (GPT-4o-mini)", role: "احتياطي + تحليل الأخبار" },
      { name: "Rule-based", role: "احتياطي بدون LLM (مؤشرات فقط)" },
      { name: "Twelve Data", role: "أسعار الفوركس + الأخبار الفورية" },
      { name: "MetaTrader 5", role: "تنفيذ الصفقات على FundedNext" },
    ],
  },
  {
    title: "ForexVPS Stack (24/7)",
    subtitle: "على ForexVPS — التشغيل الدائم",
    color: "#fb923c",
    rows: [
      { name: "MT5 Desktop", role: "يتصل بسيرفر البروكر على الـ VPS" },
      { name: "mt5_windows_bridge.py", role: "جسر Python على :5555 (localhost)" },
      { name: "Brain (FastAPI)", role: "وكلاء الذكاء على :8000" },
      { name: "API + Dashboard", role: "واجهة + API على :8080" },
      { name: "cloudflared", role: "رابط هاتف عام https://….trycloudflare.com" },
      { name: "windows\\vps\\start-forexvps.bat", role: "تشغيل الكل بضغطة واحدة" },
    ],
  },
  {
    title: "Safety Layers (×7)",
    subtitle: "طبقات الحماية السبع",
    color: "#34d399",
    rows: [
      { name: "Prop Rules Layer", role: "تجاوز حدود FundedNext (4% / 9%)" },
      { name: "Execution Variance Layer", role: "تقليل تشابه التنفيذ بين حسابات المالك (معطّل افتراضياً)" },
      { name: "Correlation Guard", role: "صفقات مرتبطة بنفس الاتجاه" },
      { name: "Economic Calendar", role: "التداول وقت الأخبار الكبرى" },
      { name: "Volatility Regime", role: "تكبير الحجم وقت التذبذب العالي" },
      { name: "SL Enforcer", role: "أي صفقة بدون Stop Loss" },
      { name: "Min Hold Timer", role: "إغلاق صفقة قبل 60 ثانية" },
    ],
  },
  {
    title: "Code & Environment",
    subtitle: "إدارة الكود والبيئة",
    color: "#cbd5e1",
    rows: [
      { name: "pnpm Workspaces", role: "إدارة مشروع متعدّد الحزم" },
      { name: "Node.js 24 + Python 3.11", role: "بيئات التشغيل" },
      { name: "Drizzle ORM", role: "قاعدة البيانات (للمستقبل)" },
      { name: "TanStack Query", role: "تحديث الواجهة كل 30 ثانية" },
    ],
  },
];

const NUMBERS: Row[] = [
  { name: "لغات البرمجة", role: "3 (TypeScript, Python, Bash)" },
  { name: "الخدمات الخارجية", role: "4 (Twelve Data, OpenRouter, OpenAI, MT5)" },
  { name: "طبقات الحماية", role: "7" },
  { name: "وكلاء الذكاء الاصطناعي", role: "6" },
  { name: "الأزواج المراقبة", role: "19 زوج فوركس" },
  { name: "المؤشرات الفنية", role: "12 مؤشر" },
  { name: "الإطارات الزمنية", role: "4 (M15, H1, H4, D1)" },
  { name: "نقاط الـ API", role: "+15 endpoint" },
];

const COSTS: Row[] = [
  { name: "Replit (الاستضافة)", role: "حسب الباقة" },
  { name: "Twelve Data", role: "مجاناً (Free tier)" },
  { name: "OpenRouter (GPT/Claude)", role: "~2-5 $/شهر" },
  { name: "MT5 Demo", role: "مجاناً" },
  { name: "ForexVPS (دائم)", role: "حسب باقة الاشتراك" },
  { name: "الإجمالي الحالي", role: "VPS + OpenRouter ~2-5 $" },
];

function escapeHtml(s: string): string {
  return s
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

function renderSection(s: Section): string {
  const rows = s.rows
    .map(
      (r) => `
    <tr>
      <td class="name">${escapeHtml(r.name)}</td>
      <td class="role">${escapeHtml(r.role)}</td>
    </tr>`
    )
    .join("");
  return `
  <section class="card">
    <div class="card-head" style="border-color:${s.color}66;background:${s.color}10;">
      <div class="dot" style="background:${s.color};"></div>
      <div class="titles">
        <div class="title">${escapeHtml(s.title)}</div>
        <div class="subtitle">${escapeHtml(s.subtitle)}</div>
      </div>
      <div class="count">${s.rows.length}</div>
    </div>
    <table>${rows}</table>
  </section>`;
}

function renderMini(title: string, subtitle: string, color: string, rows: Row[]): string {
  const trs = rows
    .map(
      (r) => `
    <tr>
      <td class="role">${escapeHtml(r.name)}</td>
      <td class="num">${escapeHtml(r.role)}</td>
    </tr>`
    )
    .join("");
  return `
  <section class="card">
    <div class="card-head" style="border-color:${color}66;background:${color}10;">
      <div class="dot" style="background:${color};"></div>
      <div class="titles">
        <div class="title">${escapeHtml(title)}</div>
        <div class="subtitle">${escapeHtml(subtitle)}</div>
      </div>
    </div>
    <table>${trs}</table>
  </section>`;
}

router.get("/tools", (_req, res) => {
  const sectionsHtml = SECTIONS.map(renderSection).join("\n");
  const numbersHtml = renderMini("Totals", "الأرقام الإجمالية", "#22d3ee", NUMBERS);
  const costsHtml = renderMini("Monthly Cost", "التكلفة الشهرية", "#4ade80", COSTS);

  const html = `<!DOCTYPE html>
<html lang="ar" dir="rtl">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Matrix Robot — Tools & Platforms</title>
<style>
  * { box-sizing: border-box; }
  body {
    margin: 0;
    background: #0a0a0b;
    color: #e5e7eb;
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Tahoma, Arial, sans-serif;
    padding: 16px;
  }
  .wrap { max-width: 760px; margin: 0 auto; }
  header {
    background: linear-gradient(135deg, #1e293b, #0f172a);
    border: 1px solid #334155;
    border-radius: 12px;
    padding: 16px;
    margin-bottom: 16px;
    text-align: center;
  }
  header h1 { margin: 0; font-size: 20px; color: #f1f5f9; }
  header p { margin: 4px 0 0; font-size: 12px; color: #94a3b8; }
  .actions { margin-top: 12px; display: flex; gap: 8px; justify-content: center; flex-wrap: wrap; }
  .btn {
    display: inline-block; text-decoration: none;
    padding: 8px 14px; border-radius: 8px;
    background: #0ea5e9; color: white; font-weight: 600; font-size: 12px;
    border: none; cursor: pointer;
  }
  .btn.secondary { background: #334155; color: #e5e7eb; }
  .card {
    background: #111114;
    border: 1px solid #27272a;
    border-radius: 10px;
    margin-bottom: 12px;
    overflow: hidden;
  }
  .card-head {
    display: flex; align-items: center; gap: 10px;
    padding: 10px 12px; border-bottom: 1px solid;
  }
  .dot { width: 10px; height: 10px; border-radius: 50%; flex-shrink: 0; }
  .titles { flex: 1; min-width: 0; }
  .title { font-size: 13px; font-weight: 700; color: #f1f5f9; letter-spacing: 0.5px; text-transform: uppercase; }
  .subtitle { font-size: 11px; color: #94a3b8; margin-top: 2px; }
  .count {
    font-size: 11px; font-weight: 700;
    padding: 2px 8px; border-radius: 999px;
    background: rgba(255,255,255,0.08); color: #cbd5e1;
  }
  table { width: 100%; border-collapse: collapse; }
  td { padding: 8px 12px; font-size: 12px; vertical-align: top; border-top: 1px solid #1f1f23; }
  tr:first-child td { border-top: 0; }
  td.name { font-family: "SF Mono", Menlo, monospace; color: #f1f5f9; font-weight: 600; width: 45%; direction: ltr; text-align: left; }
  td.role { color: #cbd5e1; }
  td.num { font-family: "SF Mono", Menlo, monospace; color: #f1f5f9; font-weight: 600; text-align: left; direction: ltr; width: 40%; }
  footer { text-align: center; font-size: 10px; color: #64748b; padding: 16px 0; }
  @media print {
    @page { size: A4 portrait; margin: 6mm; }
    html, body { background: white !important; color: black !important; }
    body { padding: 0; margin: 0; font-size: 7pt; line-height: 1.15; }
    .wrap { max-width: 100%; margin: 0; }

    /* 2-column masonry-ish layout via CSS columns */
    .grid {
      column-count: 2;
      column-gap: 4mm;
    }
    .card {
      background: white !important;
      border: 0.4pt solid #999 !important;
      border-radius: 2pt;
      margin: 0 0 2mm 0;
      break-inside: avoid;
      page-break-inside: avoid;
      display: block;
      width: 100%;
    }
    .card-head {
      padding: 1mm 2mm;
      background: #eee !important;
      border-bottom: 0.4pt solid #999 !important;
      gap: 4pt;
    }
    .dot { width: 5pt; height: 5pt; }
    .title { font-size: 7.5pt; color: #000 !important; letter-spacing: 0.2pt; }
    .subtitle { font-size: 6pt; color: #444 !important; margin-top: 0; }
    .count {
      font-size: 6pt; padding: 0 4pt;
      background: #ddd !important; color: #000 !important;
    }
    table { font-size: 6.5pt; }
    td { padding: 1pt 3pt; border-top: 0.2pt solid #ddd !important; }
    td.name, td.num { color: #000 !important; font-size: 6.5pt; width: 50%; }
    td.role { color: #222 !important; font-size: 6.5pt; }

    header {
      background: white !important;
      border: 0.4pt solid #999 !important;
      padding: 2mm;
      margin: 0 0 2mm 0;
    }
    header h1 { font-size: 11pt; color: #000 !important; margin: 0; }
    header p { font-size: 7pt; color: #444 !important; margin: 1pt 0 0; }
    .actions { display: none !important; }
    footer { font-size: 6pt; color: #444 !important; padding: 1mm 0 0; }
  }
</style>
</head>
<body>
  <div class="wrap">
    <header>
      <h1>Matrix Robot — المنظومة الكاملة</h1>
      <p>قائمة شاملة بكل الأدوات والمنصات والطبقات</p>
      <div class="actions">
        <a class="btn" href="/api/download/tools-pdf" target="_blank">تحميل PDF</a>
        <button class="btn secondary" onclick="window.print()">طباعة الصفحة</button>
      </div>
    </header>

    <div class="grid">
      ${sectionsHtml}
      ${numbersHtml}
      ${costsHtml}
    </div>

    <footer>Matrix Robot — AI Trading Monitor · مايو 2026</footer>
  </div>
</body>
</html>`;

  res.setHeader("Content-Type", "text/html; charset=utf-8");
  res.setHeader("Cache-Control", "no-store");
  res.send(html);
});

export default router;
