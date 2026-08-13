"""Daily trading report — cycles, executions, rejections (for Demo review / ChatGPT)."""
from __future__ import annotations

import argparse
import json
import os
from collections import Counter
from datetime import datetime, timedelta, timezone

from config import get_settings


def _pg_pool():
    dsn = os.environ.get("DATABASE_URL") or get_settings().database_url
    if not dsn:
        return None
    try:
        from psycopg_pool import ConnectionPool
        return ConnectionPool(conninfo=dsn, min_size=1, max_size=2,
                              kwargs={"autocommit": True}, open=True, timeout=10)
    except Exception:
        return None


def _fetch_cycles(pool, since: datetime) -> list[dict]:
    with pool.connection() as conn:
        cur = conn.execute(
            """
            SELECT raw FROM cycle_logs
            WHERE started_at >= %s
            ORDER BY started_at ASC
            """,
            (since,),
        )
        return [row[0] for row in cur.fetchall() if row and row[0]]


def _fetch_outcomes(pool, since: datetime) -> list[dict]:
    with pool.connection() as conn:
        cur = conn.execute(
            """
            SELECT raw FROM trade_outcomes
            WHERE ts >= %s
            ORDER BY ts ASC
            """,
            (since,),
        )
        return [row[0] for row in cur.fetchall() if row and row[0]]


def _fetch_open_from_kv(pool) -> list[dict]:
    with pool.connection() as conn:
        cur = conn.execute(
            "SELECT value FROM kv_store WHERE key = 'open_positions' LIMIT 1"
        )
        row = cur.fetchone()
        if row and row[0]:
            val = row[0]
            if isinstance(val, list):
                return val
            if isinstance(val, dict) and "positions" in val:
                return val["positions"]
    return []


def _day_key(iso: str) -> str:
    try:
        return iso[:10]
    except Exception:
        return "unknown"


def _executed(cycle: dict) -> bool:
    ex = cycle.get("execution") or {}
    if ex.get("executed"):
        return True
    for e in cycle.get("executions") or []:
        if e.get("executed"):
            return True
    return False


def _decision_summary(cycle: dict) -> str:
    d = cycle.get("decision") or {}
    action = d.get("action", "HOLD")
    sym = d.get("symbol", "N/A")
    conf = d.get("confidence")
    parts = [f"{action} {sym}"]
    if conf is not None:
        parts.append(f"({conf})")
    return " ".join(parts)


def _hold_reason(cycle: dict) -> str:
    d = cycle.get("decision") or {}
    ex = cycle.get("execution") or {}
    risk = cycle.get("risk") or {}
    if risk.get("approved") is False and risk.get("reason"):
        return str(risk["reason"])[:200]
    if d.get("reasoning"):
        return str(d["reasoning"])[:200]
    if ex.get("message"):
        return str(ex["message"])[:200]
    return ""


def build_report(days: int = 2) -> str:
    settings = get_settings()
    since = datetime.now(timezone.utc) - timedelta(days=days)
    lines: list[str] = []

    lines.append("# Matrix Robot — تقرير الصفقات والدورات")
    lines.append("")
    lines.append(f"**Generated (UTC):** {datetime.now(timezone.utc).isoformat()}")
    lines.append(f"**Window:** last {days} day(s) from {since.isoformat()}")
    lines.append(f"**Mode:** {settings.trading_state}")
    lines.append(f"**Symbols configured:** {len(settings.symbol_list)} ({settings.symbols[:80]}...)")
    lines.append(f"**Smart Watcher:** {getattr(settings, 'smart_watcher_enabled', False)}")
    lines.append(f"**Off-session execute:** {getattr(settings, 'smart_watcher_execute_off_session_small', False)}")
    lines.append(f"**Min strength SMALL:** {getattr(settings, 'small_trade_min_strength', '?')}")
    lines.append(f"**Min strength NORMAL:** {getattr(settings, 'normal_trade_min_strength', '?')}")
    lines.append("")

    pool = _pg_pool()
    cycles: list[dict] = []
    outcomes: list[dict] = []
    open_pos: list[dict] = []

    if pool:
        try:
            cycles = _fetch_cycles(pool, since)
            outcomes = _fetch_outcomes(pool, since)
            open_pos = _fetch_open_from_kv(pool)
        except Exception as e:
            lines.append(f"⚠️ Postgres query error: {e}")
            lines.append("")
    else:
        from tools import memory
        hist = memory.retrieve("cycle_history") or []
        cycles = [c for c in hist if (c.get("started_at") or "") >= since.isoformat()]
        outcomes = memory.get_recent_outcomes(limit=100)
        outcomes = [o for o in outcomes if (o.get("ts") or "") >= since.isoformat()]
        open_pos = memory.retrieve("open_positions") or []

    by_day: dict[str, list[dict]] = {}
    for c in cycles:
        by_day.setdefault(_day_key(c.get("started_at", "")), []).append(c)

    executed_cycles = [c for c in cycles if _executed(c)]
    holds = len(cycles) - len(executed_cycles)
    type_counts = Counter(c.get("cycle_type", "full") for c in cycles)

    lines.append("## ملخص عام")
    lines.append("")
    lines.append(f"| Metric | Value |")
    lines.append(f"|--------|-------|")
    lines.append(f"| Total cycles | {len(cycles)} |")
    lines.append(f"| Executed (opened) | {len(executed_cycles)} |")
    lines.append(f"| HOLD / no fill | {holds} |")
    lines.append(f"| Closed trades logged | {len(outcomes)} |")
    lines.append(f"| Open positions now | {len(open_pos)} |")
    lines.append("")
    lines.append("**Cycle types:** " + ", ".join(f"{k}={v}" for k, v in sorted(type_counts.items())))
    lines.append("")

    for day in sorted(by_day.keys()):
        day_cycles = by_day[day]
        day_exec = [c for c in day_cycles if _executed(c)]
        lines.append(f"## يوم {day}")
        lines.append("")
        lines.append(f"- دورات: **{len(day_cycles)}** | تنفيذ: **{len(day_exec)}** | HOLD: **{len(day_cycles) - len(day_exec)}**")
        lines.append("")
        lines.append("| الوقت (UTC) | cycle_id | type | قرار | تنفيذ؟ | سبب HOLD / ملاحظة |")
        lines.append("|-------------|----------|------|------|--------|-------------------|")
        for c in day_cycles:
            t = (c.get("started_at") or "")[11:16]
            cid = c.get("cycle_id", "")[:8]
            ctype = c.get("cycle_type", "full")
            dec = _decision_summary(c)
            did = "✅" if _executed(c) else "HOLD"
            reason = _hold_reason(c).replace("|", "/")[:120]
            ex = c.get("execution") or {}
            if _executed(c) and ex.get("message"):
                reason = str(ex.get("message", ""))[:120]
            lines.append(f"| {t} | {cid} | {ctype} | {dec} | {did} | {reason} |")
        lines.append("")

    if outcomes:
        lines.append("## صفقات مُغلقة (trade_outcomes)")
        lines.append("")
        lines.append("| الوقت | ticket | symbol | side | pnl | reason |")
        lines.append("|-------|--------|--------|------|-----|--------|")
        for o in outcomes:
            lines.append(
                f"| {(o.get('ts') or '')[:16]} | {o.get('ticket','')} | {o.get('symbol','')} "
                f"| {o.get('side','')} | {o.get('pnl','')} | {(o.get('reason') or '')[:40]} |"
            )
        lines.append("")

    if open_pos:
        lines.append("## صفقات مفتوحة الآن")
        lines.append("")
        for p in open_pos:
            lines.append(
                f"- {p.get('symbol')} {p.get('action', p.get('side', ''))} "
                f"lots={p.get('lots')} entry={p.get('entry_price')} "
                f"SL={p.get('stop_loss')} TP={p.get('take_profit')} id={p.get('trade_id', p.get('ticket'))}"
            )
        lines.append("")

    lines.append("## لماذا قد تكون الصفقات قليلة؟ (تفسير تقني)")
    lines.append("")
    lines.append("1. **انتقائية بالتصميم** — Supervisor + Risk يرفضان أغلب الإشارات الضعيفة.")
    lines.append("2. **عتبات القوة** — SMALL يحتاج ~0.60+، NORMAL ~0.68+، off-session يحتاج 0.80+.")
    lines.append("3. **دورة واحدة ≈ قرار واحد** — لا يفتح عشرات الصفقات كل cycle.")
    lines.append("4. **Smart Watcher** — خارج الجلسة scanner رخيص + تنفيذ فقط عند فرصة قوية.")
    lines.append("5. **عدد الرموز** — V10 v3 افتراضي ~25 زوجاً وليس 55 (تحقق من symbols في config).")
    lines.append("6. **فترة التشغيل** — إذا Brain شُغّل اليوم فقط، البيانات محدودة بعدد الساعات.")
    lines.append("")

    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="Matrix Robot daily report")
    parser.add_argument("--days", type=int, default=2, help="Look back N days (default 2)")
    parser.add_argument("-o", "--output", type=str, default="", help="Write to file")
    args = parser.parse_args()
    text = build_report(days=args.days)
    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            f.write(text)
        print(f"Wrote {args.output}")
    else:
        print(text)


if __name__ == "__main__":
    main()
