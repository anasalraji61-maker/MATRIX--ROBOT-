import {
  useGetSystemStack,
  getGetSystemStackQueryKey,
} from "@workspace/api-client-react";
import type { StackService } from "@workspace/api-client-react";
import { Skeleton } from "@/components/ui/skeleton";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent } from "@/components/ui/card";
import {
  CheckCircle2,
  XCircle,
  AlertCircle,
  Layers,
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

// ── Service category icons & colors ──────────────────────────────────────
const CATEGORY_CONFIG: Record<
  string,
  { color: string; bg: string; border: string }
> = {
  Trading:          { color: "text-emerald-400", bg: "bg-emerald-500/10", border: "border-emerald-500/20" },
  "Market Data":    { color: "text-blue-400",    bg: "bg-blue-500/10",    border: "border-blue-500/20"    },
  "LLM / AI":       { color: "text-purple-400",  bg: "bg-purple-500/10",  border: "border-purple-500/20"  },
  "Agent Framework":{ color: "text-amber-400",   bg: "bg-amber-500/10",   border: "border-amber-500/20"   },
  Sentiment:        { color: "text-sky-400",      bg: "bg-sky-500/10",     border: "border-sky-500/20"     },
  "Memory / Storage":{ color: "text-orange-400", bg: "bg-orange-500/10",  border: "border-orange-500/20"  },
};

const SERVICE_INITIALS: Record<string, string> = {
  mt5:          "MT5",
  polygon:      "POL",
  openrouter:   "OR",
  openai:       "OAI",
  finbert:      "FIN",
  langchain:    "LC",
  fastapi:      "FA",
  "python-agents": "PY",
  brand24:      "B24",
  redis:        "RDS",
  supabase:     "SB",
  postgres:     "PG",
  pgvector:     "PGV",
};

function StatusBadge({ status }: { status: StackService["status"] }) {
  if (status === "active") {
    return (
      <Badge variant="outline" className="text-[10px] px-1.5 py-0 bg-emerald-500/10 text-emerald-400 border-emerald-500/30 gap-0.5">
        <CheckCircle2 className="h-2.5 w-2.5" /> Active
      </Badge>
    );
  }
  if (status === "configured") {
    return (
      <Badge variant="outline" className="text-[10px] px-1.5 py-0 bg-blue-500/10 text-blue-400 border-blue-500/30 gap-0.5">
        <CheckCircle2 className="h-2.5 w-2.5" /> Configured
      </Badge>
    );
  }
  if (status === "partial") {
    return (
      <Badge variant="outline" className="text-[10px] px-1.5 py-0 bg-amber-500/10 text-amber-400 border-amber-500/30 gap-0.5">
        <AlertCircle className="h-2.5 w-2.5" /> Partial
      </Badge>
    );
  }
  return (
    <Badge variant="outline" className="text-[10px] px-1.5 py-0 bg-secondary text-muted-foreground border-border gap-0.5">
      <XCircle className="h-2.5 w-2.5" /> Not set
    </Badge>
  );
}

function ServiceCard({ service }: { service: StackService }) {
  const cat = CATEGORY_CONFIG[service.category] ?? {
    color: "text-muted-foreground",
    bg: "bg-secondary/30",
    border: "border-border/50",
  };
  const initials = SERVICE_INITIALS[service.id] ?? service.name.slice(0, 3).toUpperCase();

  return (
    <Card
      className={`bg-card/40 border-border/50 overflow-hidden transition-colors ${
        service.configured ? "border-l-2 " + cat.border : ""
      }`}
      data-testid={`card-stack-${service.id}`}
    >
      <CardContent className="p-3 flex items-start gap-3">
        {/* Avatar */}
        <div
          className={`shrink-0 h-9 w-9 rounded-lg flex items-center justify-center text-[10px] font-bold font-mono ${cat.bg} ${cat.color} border ${cat.border}`}
        >
          {initials}
        </div>

        {/* Info */}
        <div className="flex-1 min-w-0 space-y-1">
          <div className="flex items-center justify-between gap-2">
            <span className="text-sm font-semibold truncate">{service.name}</span>
            <StatusBadge status={service.status} />
          </div>
          <p className="text-[11px] text-muted-foreground leading-snug line-clamp-2">
            {service.description}
          </p>
          {!service.configured && service.setupHint && (
            <p className="text-[10px] text-amber-400/70 font-mono leading-snug truncate">
              {service.setupHint}
            </p>
          )}
        </div>
      </CardContent>
    </Card>
  );
}

export default function SystemStack() {
  const { data: stack, isLoading } = useGetSystemStack({
    query: { refetchInterval: 60_000, queryKey: getGetSystemStackQueryKey() },
  });

  if (isLoading) {
    return (
      <div className="p-4 space-y-6">
        <Skeleton className="h-16 rounded-xl" />
        {[...Array(4)].map((_, i) => (
          <div key={i} className="space-y-2">
            <Skeleton className="h-5 w-32" />
            <Skeleton className="h-16 rounded-lg" />
            <Skeleton className="h-16 rounded-lg" />
          </div>
        ))}
      </div>
    );
  }

  if (!stack) return null;

  const pct = Math.round((stack.configuredCount / stack.totalCount) * 100);
  const byCategory: Record<string, StackService[]> = {};
  for (const svc of stack.services) {
    if (!byCategory[svc.category]) byCategory[svc.category] = [];
    byCategory[svc.category].push(svc);
  }

  return (
    <div className="p-4 flex flex-col gap-6 max-w-3xl mx-auto pb-16">
      {/* Summary card */}
      <Card className="bg-card/50 border-border/50">
        <CardContent className="p-4 space-y-3">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              <Layers className="h-4 w-4 text-primary" />
              <span className="text-sm font-semibold">System Architecture</span>
            </div>
            <span className="text-sm font-bold font-mono text-foreground">
              {stack.configuredCount}
              <span className="text-muted-foreground font-normal"> / {stack.totalCount}</span>
            </span>
          </div>

          {/* Progress bar */}
          <div className="space-y-1.5">
            <div className="flex justify-between text-[10px] text-muted-foreground font-mono">
              <span>Services configured</span>
              <span>{pct}%</span>
            </div>
            <div className="h-2 rounded-full bg-secondary overflow-hidden">
              <div
                className={`h-full rounded-full transition-all ${
                  pct === 100
                    ? "bg-emerald-500"
                    : pct >= 50
                    ? "bg-blue-500"
                    : "bg-amber-500"
                }`}
                style={{ width: `${pct}%` }}
              />
            </div>
          </div>

          {/* Category summary dots */}
          <div className="flex flex-wrap gap-2 pt-1">
            {stack.categories.map((cat) => {
              const cfg = CATEGORY_CONFIG[cat];
              const svcs = byCategory[cat] ?? [];
              const done = svcs.filter((s) => s.configured).length;
              return (
                <div
                  key={cat}
                  className={`flex items-center gap-1 text-[10px] px-2 py-1 rounded-full border ${cfg?.bg ?? ""} ${cfg?.border ?? "border-border/30"} ${cfg?.color ?? "text-muted-foreground"}`}
                >
                  <span className="font-medium">{cat}</span>
                  <span className="opacity-60">{done}/{svcs.length}</span>
                </div>
              );
            })}
          </div>
        </CardContent>
      </Card>

      {/* Services by category */}
      {stack.categories.map((category) => {
        const svcs = byCategory[category] ?? [];
        const cfg = CATEGORY_CONFIG[category];
        return (
          <section key={category}>
            <h2
              className={`text-xs font-semibold uppercase tracking-wider mb-3 flex items-center gap-2 ${cfg?.color ?? "text-muted-foreground"}`}
            >
              <span
                className={`inline-block h-1.5 w-1.5 rounded-full ${cfg?.bg ?? ""} ring-1 ${cfg?.border ?? ""}`}
              />
              {category}
            </h2>
            <div className="space-y-2">
              {svcs.map((svc) => (
                <ServiceCard key={svc.id} service={svc} />
              ))}
            </div>
          </section>
        );
      })}

      <ToolsCatalog />
    </div>
  );
}

// ─── Full Tools/Platforms Catalog (mirrors the PDF) ─────────────────────────

type CatalogRow = { name: string; role: string };
type CatalogSection = {
  title: string;
  subtitle: string;
  icon: React.ComponentType<{ className?: string }>;
  accent: string;
  rows: CatalogRow[];
};

const CATALOG_SECTIONS: CatalogSection[] = [
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
      { name: "Polygon.io", role: "مزوّد أسعار الفوركس + الأخبار" },
      { name: "OpenRouter.ai", role: "بوابة الوصول لنماذج LLM" },
      { name: "Anthropic Claude 3.5", role: "النموذج الأساسي للقرارات" },
      { name: "OpenAI GPT-4o-mini", role: "النموذج الاحتياطي" },
      { name: "Cloudflare (cloudflared)", role: "نفق يربط اللابتوب بـ Replit" },
      { name: "Contabo VPS S", role: "خادم Windows مستقبلاً (8.50$/شهر)" },
      { name: "GitHub", role: "مستودع الكود وحفظ النسخ" },
      { name: "Tailscale Funnel", role: "بديل دائم لـ cloudflared (مجاناً)" },
    ],
  },
  {
    title: "Cloud Stack",
    subtitle: "الجزء السحابي (Replit 24/7)",
    icon: Cloud,
    accent: "text-blue-400 border-blue-500/30 bg-blue-500/10",
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
    icon: Bot,
    accent: "text-amber-400 border-amber-500/30 bg-amber-500/10",
    rows: [
      { name: "Data Agent", role: "أسعار الفوركس والأخبار من Polygon" },
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
      { name: "OpenRouter (Claude 3.5)", role: "المحلّل الأساسي" },
      { name: "OpenAI (GPT-4o-mini)", role: "احتياطي + تحليل الأخبار" },
      { name: "Rule-based", role: "احتياطي بدون LLM" },
      { name: "Polygon.io", role: "أسعار الفوركس + الأخبار" },
      { name: "MetaTrader 5", role: "تنفيذ الصفقات على FundedNext" },
    ],
  },
  {
    title: "Laptop Stack",
    subtitle: "على اللابتوب — مؤقت قبل VPS",
    icon: Laptop,
    accent: "text-orange-400 border-orange-500/30 bg-orange-500/10",
    rows: [
      { name: "MT5 Desktop", role: "يتصل بسيرفر البروكر" },
      { name: "mt5_windows_bridge.py", role: "جسر Python يحوّل الأوامر لـ MT5" },
      { name: "cloudflared", role: "نفق يربط اللابتوب بـ Replit" },
      { name: "START_ALL.bat", role: "يشغّل كل شيء بضغطة واحدة" },
    ],
  },
  {
    title: "Safety Layers (×6)",
    subtitle: "طبقات الحماية الست",
    icon: Shield,
    accent: "text-emerald-400 border-emerald-500/30 bg-emerald-500/10",
    rows: [
      { name: "Prop Rules Layer", role: "تجاوز حدود FundedNext (4% / 9%)" },
      { name: "Emergency Guard", role: "إغلاق تلقائي عند تجاوز السحب اليومي" },
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

const CATALOG_NUMBERS: CatalogRow[] = [
  { name: "لغات البرمجة", role: "3" },
  { name: "الخدمات الخارجية", role: "4" },
  { name: "طبقات الحماية", role: "7" },
  { name: "وكلاء الذكاء الاصطناعي", role: "6" },
  { name: "الأزواج المراقبة", role: "19 زوج" },
  { name: "المؤشرات الفنية", role: "12 مؤشر" },
  { name: "الإطارات الزمنية", role: "4 (M15-D1)" },
  { name: "نقاط الـ API", role: "+15" },
];

const CATALOG_COSTS: CatalogRow[] = [
  { name: "Replit", role: "حسب الباقة" },
  { name: "Polygon.io", role: "مجاناً" },
  { name: "OpenRouter", role: "~2-5 $/شهر" },
  { name: "MT5 Demo", role: "مجاناً" },
  { name: "كهرباء + إنترنت", role: "~5 $/شهر" },
  { name: "الإجمالي الحالي", role: "~7-10 $/شهر" },
  { name: "+ Contabo VPS", role: "+8.50 $/شهر" },
];

function CatalogCard({ section }: { section: CatalogSection }) {
  const Icon = section.icon;
  return (
    <Card className="border-border/60 bg-card/50">
      <CardContent className="p-3">
        <div className="flex items-center gap-2 mb-2">
          <div className={`p-1.5 rounded-md border ${section.accent}`}>
            <Icon className="h-3.5 w-3.5" />
          </div>
          <div className="flex-1 min-w-0">
            <div className="text-xs font-bold uppercase tracking-wider">
              {section.title}
            </div>
            <div className="text-[10px] text-muted-foreground" dir="rtl">
              {section.subtitle}
            </div>
          </div>
          <Badge variant="outline" className="text-[10px] px-1.5 py-0">
            {section.rows.length}
          </Badge>
        </div>
        <div className="divide-y divide-border/40">
          {section.rows.map((r, i) => (
            <div key={i} className="flex items-start gap-2 py-1.5">
              <div className="flex-1 min-w-0 text-[11px] font-semibold font-mono break-words">
                {r.name}
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

function CatalogMini({
  title,
  subtitle,
  rows,
  icon: Icon,
  accent,
}: {
  title: string;
  subtitle: string;
  rows: CatalogRow[];
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

function ToolsCatalog() {
  const downloadPdf = () => {
    const base = import.meta.env.BASE_URL;
    window.open(`${base}api/download/tools-pdf`, "_blank");
  };

  return (
    <section className="space-y-3 pt-4 border-t border-border/40">
      <h2 className="text-xs font-semibold uppercase tracking-wider text-primary flex items-center gap-2">
        <span className="inline-block h-1.5 w-1.5 rounded-full bg-primary" />
        Tools & Platforms Catalog
      </h2>

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

      {CATALOG_SECTIONS.map((s) => (
        <CatalogCard key={s.title} section={s} />
      ))}

      <CatalogMini
        title="Totals"
        subtitle="الأرقام الإجمالية"
        rows={CATALOG_NUMBERS}
        icon={BarChart3}
        accent="text-cyan-400 border-cyan-500/30 bg-cyan-500/10"
      />

      <CatalogMini
        title="Monthly Cost"
        subtitle="التكلفة الشهرية"
        rows={CATALOG_COSTS}
        icon={DollarSign}
        accent="text-green-400 border-green-500/30 bg-green-500/10"
      />

      <div className="text-[10px] text-center text-muted-foreground py-2">
        Matrix Robot — AI Trading Monitor · مايو 2026
      </div>
    </section>
  );
}
