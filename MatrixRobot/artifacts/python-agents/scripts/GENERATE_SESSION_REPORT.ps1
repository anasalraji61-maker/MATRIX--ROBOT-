"""Session trade report — since midnight (broker server time) for ChatGPT review."""
from __future__ import annotations

import argparse
import json
import os
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone

from config import get_settings
from tools.prop_time import prop_server_now


def _pg_pool():
    dsn = os.environ.get("DATABASE_URL") or get_settings().database_url
    if not dsn:
        return None
    try:
        from psycopg_pool import ConnectionPool
        return ConnectionPool(
            conninfo=dsn, min_size=1, max_size=2,
            kwargs={"autocommit": True}, open=True, timeout=15,
        )
    except Exception:
        return None


def _since_midnight_utc() -> datetime:
    """Midnight in broker/prop server time, converted to UTC for DB queries."""
    s = get_settings()
    off = int(getattr(s, "prop_server_utc_offset_hours", 3))
    server_now = datetime.now(timezone.utc) + timedelta(hours=off)
    server_midnight = server_now.replace(hour=0, minute=0, second=0, microsecond=0)
    return server_midnight - timedelta(hours=off)


def _fetch_outcomes(pool, since: datetime) -> list[dict]:
    with pool.connection() as conn:
        cur = conn.execute(
            "SELECT raw FROM trade_outcomes WHERE ts >= %s ORDER BY ts ASC",
            (since,),
        )
        return [row[0] for row in cur.fetchall() if row and row[0]]


def _fetch_cycles(pool, since: datetime) -> list[dict]:
    with pool.connection() as conn:
        cur = conn.execute(
            "SELECT raw FROM cycle_logs WHERE started_at >= %s ORDER BY started_at ASC",
            (since,),
        )
        return [row[0] for row in cur.fetchall() if row and row[0]]


def _pnl_bucket(outcomes: list[dict]) -> dict:
    wins = [o for o in outcomes if (o.get("pnl") or 0) > 0]
    losses = [o for o in outcomes if (o.get("pnl") or 0) < 0]
    flat = [o for o in outcomes if (o.get("pnl") or 0) == 0]
    gross_win = sum(float(o["pnl"]) for o in wins)
    gross_loss = sum(float(o["pnl"]) for o in losses)
    net = gross_win + gross_loss
    n = len(wins) + len(losses)
    return {
        "closed": len(outcomes),
        "wins": len(wins),
        "losses": len(losses),
        "flat": len(flat),
        "gross_profit": round(gross_win, 2),
        "gross_loss": round(gross_loss, 2),
        "net_pnl": round(net, 2),
        "win_rate": round(len(wins) / n, 4) if n else None,
        "avg_win": round(gross_win / len(wins), 2) if wins else 0,
        "avg_loss": round(gross_loss / len(losses), 2) if losses else 0,
        "profit_factor": round(gross_win / abs(gross_loss), 2) if gross_loss else None,
    }


def build_report(since: datetime | None = None) -> str:
    settings = get_settings()
    since = since or _since_midnight_utc()
    now_utc = datetime.now(timezone.utc)
    server_now = prop_server_now()

    lines: list[str] = []
    lines.append("# Matrix Robot V11 — تقرير جلسة التداول (لـ ChatGPT)")
    lines.append("")
    lines.append(f"**Generated UTC:** {now_utc.isoformat()}")
    lines.append(f"**Broker server now:** {server_now.strftime('%Y-%m-%d %H:%M')} (offset UTC+{getattr(settings, 'prop_server_utc_offset_hours', 3)})")
    lines.append(f"**Window:** من منتصف الليل (server) = `{since.isoformat()}` → الآن")
    lines.append(f"**Profile:** {getattr(settings, 'trading_mode_profile', 'N/A')}")
    lines.append(f"**Mode:** {settings.trading_state}")
    lines.append(f"**Scalping:** {settings.scalping_mode} | **Council:** {getattr(settings, 'council_mode', 'N/A')}")
    lines.append(f"**Symbols active:** ~{len(settings.symbol_list)} | disabled: {getattr(settings, 'active_disabled_symbols', '')}")
    lines.append(f"**Caps:** max_day={settings.max_trades_per_day} max_open={settings.max_concurrent_positions} scalp_day={settings.scalping_max_trades_per_day}")
    lines.append("")

    pool = _pg_pool()
    outcomes: list[dict] = []
    cycles: list[dict] = []

    if pool:
        try:
            outcomes = _fetch_outcomes(pool, since)
            cycles = _fetch_cycles(pool, since)
        except Exception as e:
            lines.append(f"⚠️ Postgres error: {e}")
            lines.append("")
    else:
        from tools import memory
        outcomes = [
            o for o in (memory.get_recent_outcomes(limit=500) or [])
            if (o.get("ts") or "") >= since.isoformat()
        ]
        hist = memory.retrieve("cycle_history") or []
        cycles = [c for c in hist if (c.get("started_at") or "") >= since.isoformat()]

    stats = _pnl_bucket(outcomes)
    lines.append("## 1. ملخص P&L (صفقات مُغلقة)")
    lines.append("")
    lines.append("| Metric | Value |")
    lines.append("|--------|-------|")
    for k, v in stats.items():
        lines.append(f"| {k} | {v} |")
    lines.append("")

    if outcomes:
        by_sym: dict[str, list[float]] = defaultdict(list)
        by_reason: Counter = Counter()
        by_side: dict[str, list[float]] = defaultdict(list)
        by_hour: Counter = Counter()

        for o in outcomes:
            sym = str(o.get("symbol") or "?")
            pnl = float(o.get("pnl") or 0)
            by_sym[sym].append(pnl)
            by_reason[str(o.get("reason") or "unknown")] += 1
            by_side[str(o.get("side") or "?")].append(pnl)
            ts = str(o.get("ts") or "")
            if len(ts) >= 13:
                by_hour[ts[11:13] + ":00 UTC"] += 1

        lines.append("## 2. حسب الرمز")
        lines.append("")
        lines.append("| Symbol | Trades | W | L | Net PnL | Win% |")
        lines.append("|--------|--------|---|---|---------|------|")
        sym_rows = []
        for sym, pnls in by_sym.items():
            w = sum(1 for p in pnls if p > 0)
            l = sum(1 for p in pnls if p < 0)
            sym_rows.append((sym, len(pnls), w, l, round(sum(pnls), 2), round(w / len(pnls), 2) if pnls else 0))
        for row in sorted(sym_rows, key=lambda x: x[4]):
            lines.append(f"| {row[0]} | {row[1]} | {row[2]} | {row[3]} | {row[4]} | {row[5]} |")
        lines.append("")

        lines.append("## 3. سبب الإغلاق (MT5)")
        lines.append("")
        for reason, cnt in by_reason.most_common():
            lines.append(f"- **{reason}**: {cnt}")
        lines.append("")

        lines.append("## 4. أفضل / أسوأ 10 صفقات")
        lines.append("")
        sorted_o = sorted(outcomes, key=lambda x: float(x.get("pnl") or 0))
        lines.append("### خاسرة")
        for o in sorted_o[:10]:
            lines.append(
                f"- {o.get('ts','')[:16]} | {o.get('symbol')} {o.get('side')} "
                f"pnl={o.get('pnl')} reason={o.get('reason')} ticket={o.get('ticket')}"
            )
        lines.append("")
        lines.append("### رابحة")
        for o in sorted_o[-10:][::-1]:
            lines.append(
                f"- {o.get('ts','')[:16]} | {o.get('symbol')} {o.get('side')} "
                f"pnl={o.get('pnl')} reason={o.get('reason')} ticket={o.get('ticket')}"
            )
        lines.append("")

        lines.append("## 5. كل الصفقات المُغلقة (تفصيلي)")
        lines.append("")
        lines.append("| time | ticket | symbol | side | pnl | reason | entry | exit |")
        lines.append("|------|--------|--------|------|-----|--------|-------|------|")
        for o in outcomes:
            lines.append(
                f"| {(o.get('ts') or '')[:19]} | {o.get('ticket','')} | {o.get('symbol','')} "
                f"| {o.get('side','')} | {o.get('pnl','')} | {o.get('reason','')} "
                f"| {o.get('entry','')} | {o.get('exit','')} |"
            )
        lines.append("")
    else:
        lines.append("⚠️ لا توجد صفقات مُغلقة مسجّلة في trade_outcomes لهذه الفترة.")
        lines.append("")

    if cycles:
        executed = sum(
            1 for c in cycles
            if (c.get("execution") or {}).get("executed")
            or any((e.get("executed") for e in (c.get("executions") or [])))
        )
        hold_reasons: Counter = Counter()
        for c in cycles:
            if not (c.get("execution") or {}).get("executed"):
                r = (c.get("risk") or {}).get("reason") or (c.get("decision") or {}).get("reasoning") or "hold"
                hold_reasons[str(r)[:80]] += 1

        lines.append("## 6. الدورات (cycles)")
        lines.append("")
        lines.append(f"- Total cycles: **{len(cycles)}**")
        lines.append(f"- Opened trades (cycles with execution): **{executed}**")
        lines.append(f"- HOLD cycles: **{len(cycles) - executed}**")
        lines.append("")
        lines.append("**Top HOLD reasons:**")
        for reason, cnt in hold_reasons.most_common(8):
            lines.append(f"- {reason}: {cnt}")
        lines.append("")

    lines.append("## 7. ملاحظات للمراجعة (ChatGPT)")
    lines.append("")
    lines.append("- V11 Full Power: scalping enforce + 52 symbols + 24h → عدد صفقات أعلى من V10.")
    lines.append("- خسائر صغيرة متعددة مع ربح صافي إيجابي = win rate منخفض لكن R:R إجمالي جيد.")
    lines.append("- راجع رموز بـ win% منخفض — قد تحتاج quarantine مؤقت أو رفع min_strength لها.")
    lines.append("- راجع stop_loss vs take_profit في سبب الإغلاق — كثرة SL = دخول مبكر أو SL ضيق.")
    lines.append("- اقتراحات ضبط (لا تطبّق قبل مراجعة): SCALPING_MIN_STRENGTH 0.58→0.63, MIN_RR 1.05→1.15, ML_FILTER enforce.")
    lines.append("")

    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="Session trade report since midnight")
    parser.add_argument("--hours", type=float, default=0, help="Look back N hours instead of since midnight")
    parser.add_argument("-o", "--output", type=str, default="SESSION_TRADE_REPORT.md")
    args = parser.parse_args()

    since = _since_midnight_utc()
    if args.hours > 0:
        since = datetime.now(timezone.utc) - timedelta(hours=args.hours)

    text = build_report(since)
    with open(args.output, "w", encoding="utf-8") as f:
        f.write(text)
    print(f"Wrote {args.output}")
    print(f"Closed trades in window: see report")


if __name__ == "__main__":
    main()
