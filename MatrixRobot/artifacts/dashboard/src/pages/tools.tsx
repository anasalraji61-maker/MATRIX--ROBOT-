import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import {
  Globe,
  Cloud,
  Bot,
  Database,
  Laptop,
  Shield,
  Wrench,
  BarChart3,
  DollarSign,
} from "lucide-react";

type Row = { name: string; role: string };

type Section = {
  title: string;
  subtitle?: string;
  icon: React.ComponentType<{ className?: string }>;
  accent: string;
  rows: Row[];
};

const SECTIONS: Section[] = [
  {
    title: "Platforms & Sites",
    subtitle: "المنصات والمواقع",
    icon: Globe,
    accent: "text-sky-400 border-sky-500/30 bg-sky-500/10",
    rows: [
      { name: "Replit", role: "الاستضافة السحابية + بيئة التطوير" },
      { name: "FundedNext", role: "شركة الـ Prop Firm (التحدّي والتمويل)" },
      { name: "MetaTrader 5 (MT5)", role: "منصة التداول لدى البروكر" },
      { name: "MetaQuotes-Demo", role: "سيرفر الحساب التجريبي" },
      { name: "Twelve Data", role: "مزوّد أسعار الفوركس + الأخبار" },
      { name: "OpenRouter.ai", role: "بوابة الوصول لنماذج LLM" },
      { name: "Anthropic Claude 3.5", role: "النموذج الأساسي للقرارات" },
      { name: "OpenAI GPT-4o-mini", role: "النموذج الاحتياطي + تحليل الأخبار" },
      { name: "Cloudflare (cloudflared)", role: "نفق يربط اللابتوب بـ Replit" },
      { name: "Contabo VPS S", role: "خادم Windows مستقبلاً (8.50$/شهر)" },
      { name: "GitHub", role: "مستودع الكود وحفظ النسخ" },
      { name: "Tailscale Funnel", role: "بديل دائم لـ cloudflared (مجاناً)" },
    ],
  },
  {
    title: "Cloud Stack (Replit — 24/7)",
    subtitle: "الجزء السحابي",
    icon: Cloud,
    accent: "text-blue-400 border-blue-500/30 bg-blue-500/10",
    rows: [
      { name: "React + Vite + Tailwind", role: "الواجهة الأمامية (Dashboard)" },
      { name: "shadcn/ui", role: "مكتبة العناصر الجاهزة" },
      { name: "PWA (Progressive Web App)", role: "تطبيق على iPhone بدون App Store" },
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
    icon: Bot,
    accent: "text-amber-400 border-amber-500/30 bg-amber-500/10",
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
    icon: Database,
    accent: "text-purple-400 border-purple-500/30 bg-purple-500/10",
    rows: [
      { name: "OpenRouter (Claude 3.5)", role: "المحلّل الأساسي للقرارات" },
      { name: "OpenAI (GPT-4o-mini)", role: "احتياطي + تحليل الأخبار" },
      { name: "Rule-based", role: "احتياطي بدون LLM (مؤشرات فقط)" },
      { name: "Twelve Data", role: "أسعار الفوركس + الأخبار الفورية" },
      { name: "MetaTrader 5", role: "تنفيذ الصفقات على FundedNext" },
    ],
  },
  {
    title: "Laptop Stack (Temporary)",
    subtitle: "على اللابتوب — للنقل لـ VPS",
    icon: Laptop,
    accent: "text-orange-400 border-orange-500/30 bg-orange-500/10",
    rows: [
      { name: "MT5 Desktop", role: "يتصل بسيرفر البروكر" },
      { name: "mt5_windows_bridge.py", role: "جسر Python يحوّل أوامرنا لـ MT5" },
      { name: "cloudflared", role: "نفق يربط اللابتوب بـ Replit" },
      { name: "START_ALL.bat", role: "يشغّل كل شيء بضغطة واحدة" },
    ],
  },
  {
    title: "Safety Layers (×7)",
    subtitle: "طبقات الحماية السبع",
    icon: Shield,
    accent: "text-emerald-400 border-emerald-500/30 bg-emerald-500/10",
    rows: [
      { name: "Prop Rules Layer", role: "تجاوز حدود FundedNext (4% / 9%)" },
      { name: "Execution Variance Layer", role: "تقليل تشابه التنفيذ بين حسابات المالك بناءً على إدارة المخاطر" },
      { name: "Correlation Guard", role: "صفقات مرتبطة بنفس الاتجاه" },
      { name: "Economic Calendar", role: "التداول وقت الأخبار الكبرى" },
      { name: "Volatility Regime", role: "تقليل الحجم وقت التذبذب العالي" },
      { name: "SL Enforcer", role: "أي صفقة بدون Stop Loss" },
      { name: "Min Hold Timer", role: "إغلاق صفقة قبل 60 ثانية" },
    ],
  },
  {
    title: "Code & Environment",
    subtitle: "إدارة الكود والبيئة",
    icon: Wrench,
    accent: "text-slate-300 border-slate-500/30 bg-slate-500/10",
    rows: [
      { name: "pnpm Workspaces", role: "إدارة مشروع متعدّد الحزم" },
      { name: "Node.js 24 + Python 3.11", role: "بيئات التشغيل" },
      { name: "Drizzle ORM", role: "قاعدة البيانات (للمستقبل)" },
      { name: "TanStack Query", role: "تحديث الواجهة كل 30 ثانية" },
    ],
  },
];

const NUMBERS: Row[] = [
  { name: "لغات البرمجة", role: "3" },
  { name: "الخدمات الخارجية", role: "4" },
  { name: "طبقات الحماية", role: "7" },
  { name: "وكلاء الذكاء الاصطناعي", role: "6" },
  { name: "الأزواج المراقبة", role: "19 زوج فوركس" },
  { name: "المؤشرات الفنية", role: "12 مؤشر" },
  { name: "الإطارات الزمنية", role: "4 (M15, H1, H4, D1)" },
  { name: "نقاط الـ API", role: "+15 endpoint" },
];

const COSTS: Row[] = [
  { name: "Replit (الاستضافة)", role: "حسب الباقة" },
  { name: "Twelve Data", role: "مجاناً" },
  { name: "OpenRouter (GPT/Claude)", role: "~2-5 $/شهر" },
  { name: "MT5 Demo", role: "مجاناً" },
  { name: "اللابتوب (كهرباء + إنترنت)", role: "~5 $/شهر" },
  { name: "الإجمالي الحالي", role: "~7-10 $/شهر" },
  { name: "+ Contabo VPS (لاحقاً)", role: "+8.50 $/شهر" },
];

function SectionCard({ section }: { section: Section }) {
  const Icon = section.icon;
  return (
    <Card className="border-border/60 bg-card/50">
      <CardContent className="p-3">
        <div className="flex items-center gap-2 mb-2">
          <div className={`p-1.5 rounded-md border ${section.accent}`}>
            <Icon className="h-3.5 w-3.5" />
          </div>
          <div className="flex-1 min-w-0">
            <div className="text-xs font-bold uppercase tracking-wider text-foreground">
              {section.title}
            </div>
            {section.subtitle && (
              <div className="text-[10px] text-muted-foreground" dir="rtl">
                {section.subtitle}
              </div>
            )}
          </div>
          <Badge variant="outline" className="text-[10px] px-1.5 py-0">
            {section.rows.length}
          </Badge>
        </div>
        <div className="divide-y divide-border/40">
          {section.rows.map((r, i) => (
            <div key={i} className="flex items-start gap-2 py-1.5">
              <div className="flex-1 min-w-0">
                <div className="text-[11px] font-semibold text-foreground font-mono break-words">
                  {r.name}
                </div>
              </div>
              <div
                className="flex-1 min-w-0 text-[11px] text-muted-foreground text-right"
                dir="rtl"
              >
                {r.role}
              </div>
            </div>
          ))}
        </div>
      </CardContent>
    </Card>
  );
}

function MiniCard({
  title,
  subtitle,
  rows,
  icon: Icon,
  accent,
}: {
  title: string;
  subtitle: string;
  rows: Row[];
  icon: React.ComponentType<{ className?: string }>;
  accent: string;
}) {
  return (
    <Card className="border-border/60 bg-card/50">
      <CardContent className="p-3">
        <div className="flex items-center gap-2 mb-2">
          <div className={`p-1.5 rounded-md border ${accent}`}>
            <Icon className="h-3.5 w-3.5" />
          </div>
          <div className="flex-1 min-w-0">
            <div className="text-xs font-bold uppercase tracking-wider">
              {title}
            </div>
            <div className="text-[10px] text-muted-foreground" dir="rtl">
              {subtitle}
            </div>
          </div>
        </div>
        <div className="divide-y divide-border/40">
          {rows.map((r, i) => (
            <div key={i} className="flex items-center justify-between py-1.5">
              <div
                className="text-[11px] text-muted-foreground text-right flex-1"
                dir="rtl"
              >
                {r.name}
              </div>
              <div className="text-[11px] font-semibold font-mono">
                {r.role}
              </div>
            </div>
          ))}
        </div>
      </CardContent>
    </Card>
  );
}

export default function Tools() {
  const downloadPdf = () => {
    const base = import.meta.env.BASE_URL;
    window.open(`${base}api/download/tools-pdf`, "_blank");
  };

  return (
    <main className="p-4 flex flex-col gap-3 max-w-3xl mx-auto">
      <Card className="border-primary/30 bg-primary/5">
        <CardContent className="p-3 flex items-center justify-between gap-3">
          <div className="flex-1 min-w-0">
            <div className="text-sm font-bold">Matrix Robot — المنظومة الكاملة</div>
            <div className="text-[10px] text-muted-foreground" dir="rtl">
              قائمة شاملة بكل الأدوات والمنصات والطبقات
            </div>
          </div>
          <button
            onClick={downloadPdf}
            className="text-[10px] font-semibold uppercase tracking-wider px-3 py-1.5 rounded-md bg-primary text-primary-foreground hover:opacity-90"
            data-testid="button-download-tools-pdf"
          >
            تحميل PDF
          </button>
        </CardContent>
      </Card>

      {SECTIONS.map((s) => (
        <SectionCard key={s.title} section={s} />
      ))}

      <MiniCard
        title="Totals"
        subtitle="الأرقام الإجمالية"
        rows={NUMBERS}
        icon={BarChart3}
        accent="text-cyan-400 border-cyan-500/30 bg-cyan-500/10"
      />

      <MiniCard
        title="Monthly Cost"
        subtitle="التكلفة الشهرية"
        rows={COSTS}
        icon={DollarSign}
        accent="text-green-400 border-green-500/30 bg-green-500/10"
      />

      <div className="text-[10px] text-center text-muted-foreground py-2">
        Matrix Robot — AI Trading Monitor · مايو 2026
      </div>
    </main>
  );
}
