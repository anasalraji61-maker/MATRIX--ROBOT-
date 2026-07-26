"""V11 comprehensive trade review — midnight to now, for ChatGPT (no config changes)."""
from __future__ import annotations

import argparse
import os
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any

import httpx

from config import get_settings
from tools.prop_time import prop_server_now


STRATEGY_LABELS = {
    "ema_pullback_scalp": "EMA Pullback",
    "micro_breakout": "Micro Breakout",
    "micro_breakout_scalp": "Micro Breakout",
    "liquidity_sweep_reversal": "Liquidity Sweep",
    "asian_range_mean_reversion": "Asian Range",
    "momentum_continuation": "Momentum Continuation",
    "volatility_expansion": "Volatility Expansion",
    "volatility_expansion_scalp": "Volatility Expansion",
}

TIME_BUCKETS = [
    ("00:00–03:00", 0, 3),
    ("03:00–06:00", 3, 6),
    ("06:00–09:00", 6, 9),
    ("09:00–12:00", 9, 12),
    ("12:00–15:00", 12, 15),
    ("15:00–18:00", 15, 18),
    ("18:00–21:00", 18, 21),
    ("21:00–24:00", 21, 24),
]


@dataclass
class Trade:
    ticket: str
    symbol: str
    side: str
    pnl: float
    opened_at: str | None
    closed_at: str
    trade_tier: str
    strategy: str
    close_reason: str
    entry: float | None = None
    exit: float | None = None
    stop_loss: float | None = None
    take_profit: float | None = None
    spread_pips: float | None = None
    strength: float | None = None
    council_approved: bool | None = None
    hold_minutes: float | None = None
    entry_reason: str = ""
    skeptic_would_veto: str = "not_logged"
    source: str = "db"
    raw: dict = field(default_factory=dict)


def _pg_pool():
    dsn = os.environ.get("DATABASE_URL") or get_settings().database_url
    if not dsn:
        return None
    try:
        from psycopg_pool import ConnectionPool
        return ConnectionPool(
            conninfo=dsn, min_size=1, max_size=2,
            kwargs={"autocommit": True}, open=True, timeout=20,
        )
    except Exception:
        return None


def since_midnight_utc() -> datetime:
    s = get_settings()
    off = int(getattr(s, "prop_server_utc_offset_hours", 3))
    server_now = datetime.now(timezone.utc) + timedelta(hours=off)
    midnight = server_now.replace(hour=0, minute=0, second=0, microsecond=0)
    return midnight - timedelta(hours=off)


def _parse_ts(iso: str | None) -> datetime | None:
    if not iso:
        return None
    try:
        return datetime.fromisoformat(iso.replace("Z", "+00:00"))
    except Exception:
        return None


def _server_hour(iso: str) -> int:
    s = get_settings()
    off = int(getattr(s, "prop_server_utc_offset_hours", 3))
    dt = _parse_ts(iso)
    if not dt:
        return -1
    return (dt + timedelta(hours=off)).hour


def _time_bucket(iso: str) -> str:
    h = _server_hour(iso)
    if h < 0:
        return "unknown"
    for label, start, end in TIME_BUCKETS:
        if start <= h < end:
            return label
    return "unknown"


def _strategy_label(raw: str) -> str:
    key = (raw or "unknown").strip().lower()
    return STRATEGY_LABELS.get(key, raw or "Unknown")


def _infer_tier(o: dict, hold_min: float | None) -> str:
    tier = str(o.get("trade_tier") or "").upper()
    if tier in ("SCALP", "SMALL", "NORMAL", "SWING", "INTRADAY"):
        if tier == "SMALL":
            return "INTRADAY"
        return tier if tier != "NORMAL" else "INTRADAY"
    strat = str(o.get("strategy") or o.get("strategy_name") or "").lower()
    if "scalp" in strat or o.get("scalp_strategy"):
        return "SCALP"
    if hold_min is not None:
        if hold_min <= 45:
            return "SCALP"
        if hold_min <= 360:
            return "INTRADAY"
        return "SWING"
    return "INTRADAY"


def _hold_minutes(opened: str | None, closed: str) -> float | None:
    a, b = _parse_ts(opened), _parse_ts(closed)
    if not a or not b:
        return None
    return max(0, (b - a).total_seconds() / 60)


def _skeptic_hint(o: dict) -> str:
    strength = o.get("strength")
    spread = o.get("spread_pips") or o.get("spread_at_entry")
    if strength is not None and float(strength) < 0.60:
        return "likely_yes_weak_strength"
    if spread is not None and float(spread) > 2.5:
        return "likely_yes_wide_spread"
    if o.get("council_approved") is False:
        return "yes_council_rejected"
    return "unknown_not_logged_per_trade"


def _normalize(o: dict) -> Trade | None:
    pnl = o.get("pnl")
    if pnl is None:
        return None
    pnl = float(pnl)
    closed = str(o.get("closed_at") or o.get("ts") or "")
    opened = o.get("opened_at")
    hold = _hold_minutes(opened, closed)
    strat_raw = str(
        o.get("strategy") or o.get("strategy_name") or o.get("scalp_strategy") or "unknown"
    )
    return Trade(
        ticket=str(o.get("ticket") or o.get("trade_id") or o.get("position_id") or ""),
        symbol=str(o.get("symbol") or "?").upper(),
        side=str(o.get("side") or "?").upper(),
        pnl=pnl,
        opened_at=opened,
        closed_at=closed,
        trade_tier=_infer_tier(o, hold),
        strategy=_strategy_label(strat_raw),
        close_reason=str(o.get("reason") or o.get("close_reason") or "unknown"),
        entry=_f(o.get("entry") or o.get("entry_price")),
        exit=_f(o.get("exit") or o.get("exit_price")),
        stop_loss=_f(o.get("stop_loss") or o.get("initial_stop_loss")),
        take_profit=_f(o.get("take_profit")),
        spread_pips=_f(o.get("spread_pips") or o.get("spread_at_entry")),
        strength=_f(o.get("strength")),
        council_approved=o.get("council_approved"),
        hold_minutes=hold,
        entry_reason=str(o.get("entry_reason") or o.get("signal_reason") or "")[:120],
        skeptic_would_veto=_skeptic_hint(o),
        source=str(o.get("source") or "merged"),
        raw=o,
    )


def _f(v) -> float | None:
    if v is None:
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _fetch_db_outcomes(pool, since: datetime) -> list[dict]:
    with pool.connection() as conn:
        cur = conn.execute(
            "SELECT raw FROM trade_outcomes WHERE ts >= %s ORDER BY ts ASC",
            (since,),
        )
        return [row[0] for row in cur.fetchall() if row and row[0]]


def _fetch_bridge_closed(since: datetime) -> list[dict]:
    settings = get_settings()
    url = (settings.mt5_bridge_url or "").rstrip("/")
    if not url:
        return []
    try:
        from tools.mt5_bridge import _bridge_headers
        headers = _bridge_headers()
    except Exception:
        secret = settings.mt5_bridge_secret or ""
        headers = {"X-Bridge-Secret": secret} if secret else {}
    try:
        with httpx.Client(timeout=30) as client:
            r = client.get(f"{url}/history/closed-positions", params={"days": 2}, headers=headers)
            r.raise_for_status()
            data = r.json()
    except Exception:
        return []
    out = []
    for p in data.get("positions") or []:
        closed = p.get("closed_at") or ""
        dt = _parse_ts(closed)
        if dt and dt >= since:
            p["source"] = "mt5_bridge"
            out.append(p)
    return out


def _merge_trades(db_rows: list[dict], bridge_rows: list[dict]) -> list[Trade]:
    meta_by_ticket: dict[str, dict] = {}
    for row in db_rows:
        tid = str(row.get("ticket") or row.get("trade_id") or "")
        if tid:
            meta_by_ticket[tid] = {**meta_by_ticket.get(tid, {}), **row}

    merged: dict[str, dict] = {}
    for row in bridge_rows:
        tid = str(row.get("position_id") or row.get("ticket") or "")
        if not tid:
            continue
        base = {**meta_by_ticket.get(tid, {}), **row}
        base["ticket"] = tid
        base["pnl"] = row.get("pnl")
        base["reason"] = row.get("close_reason")
        merged[tid] = base

    for tid, row in meta_by_ticket.items():
        if tid not in merged:
            merged[tid] = row

    trades: list[Trade] = []
    for o in merged.values():
        t = _normalize(o)
        if t:
            trades.append(t)
    trades.sort(key=lambda x: x.closed_at)
    return trades


def _summary(trades: list[Trade]) -> dict[str, Any]:
    wins = [t for t in trades if t.pnl > 0]
    losses = [t for t in trades if t.pnl < 0]
    flat = [t for t in trades if t.pnl == 0]
    gw = sum(t.pnl for t in wins)
    gl = sum(t.pnl for t in losses)
    net = gw + gl
    n = len(wins) + len(losses)

    def _streaks() -> tuple[int, int]:
        max_w = max_l = cw = cl = 0
        for t in trades:
            if t.pnl > 0:
                cw += 1
                cl = 0
                max_w = max(max_w, cw)
            elif t.pnl < 0:
                cl += 1
                cw = 0
                max_l = max(max_l, cl)
            else:
                cw = cl = 0
        return max_w, max_l

    max_w, max_l = _streaks()
    return {
        "total": len(trades),
        "wins": len(wins),
        "losses": len(losses),
        "flat": len(flat),
        "win_rate": round(len(wins) / n, 4) if n else None,
        "gross_profit": round(gw, 2),
        "gross_loss": round(gl, 2),
        "net_profit": round(net, 2),
        "profit_factor": round(gw / abs(gl), 2) if gl else None,
        "avg_win": round(gw / len(wins), 2) if wins else 0,
        "avg_loss": round(gl / len(losses), 2) if losses else 0,
        "largest_win": round(max((t.pnl for t in wins), default=0), 2),
        "largest_loss": round(min((t.pnl for t in losses), default=0), 2),
        "max_consecutive_wins": max_w,
        "max_consecutive_losses": max_l,
    }


def _group_stats(trades: list[Trade], key_fn) -> list[dict]:
    groups: dict[str, list[Trade]] = defaultdict(list)
    for t in trades:
        groups[key_fn(t)].append(t)
    rows = []
    for name, ts in sorted(groups.items(), key=lambda x: sum(t.pnl for t in x[1])):
        s = _summary(ts)
        holds = [t.hold_minutes for t in ts if t.hold_minutes is not None]
        avg_hold = round(sum(holds) / len(holds), 1) if holds else None
        loss_reasons = Counter(t.close_reason for t in ts if t.pnl < 0)
        rows.append({
            "name": name,
            "stats": s,
            "avg_hold_min": avg_hold,
            "top_loss_reasons": loss_reasons.most_common(3),
        })
    return rows


def _recommendations(trades: list[Trade], by_sym, by_strat, by_time, by_tier) -> list[str]:
    recs: list[str] = []
    if not trades:
        return ["لا توجد صفقات مُغلقة في النافذة — انتظر إغلاق صفقات أو تحقق من Bridge/Postgres."]

    s = _summary(trades)
    if s["win_rate"] and s["win_rate"] < 0.45 and s["net_profit"] > 0:
        recs.append(
            f"Win rate منخفض ({s['win_rate']:.0%}) لكن صافي ربح موجب — ركّز على تقليل الخسائر الصغيرة "
            "برفع `SCALPING_MIN_STRENGTH` من 0.58 إلى 0.63 (لا تطبّق قبل مراجعة ChatGPT)."
        )

    bad_syms = [r for r in by_sym if r["stats"]["total"] >= 3 and r["stats"]["net_profit"] < 0]
    if bad_syms:
        names = ", ".join(r["name"] for r in sorted(bad_syms, key=lambda x: x["stats"]["net_profit"])[:3])
        recs.append(f"Quarantine مؤقت لأسوأ الرموز (≥3 صفقات وصافي سالب): **{names}**.")

    bad_strats = [r for r in by_strat if r["stats"]["total"] >= 3 and r["stats"]["net_profit"] < 0]
    if bad_strats:
        worst = min(bad_strats, key=lambda x: x["stats"]["net_profit"])
        recs.append(
            f"خفّف أو أوقف استراتيجية **{worst['name']}** "
            f"(net {worst['stats']['net_profit']}$, win% {worst['stats'].get('win_rate')})."
        )

    bad_hours = [r for r in by_time if r["stats"]["total"] >= 3 and r["stats"]["net_profit"] < 0]
    if bad_hours:
        worst_h = min(bad_hours, key=lambda x: x["stats"]["net_profit"])
        recs.append(
            f"فترة **{worst_h['name']}** (server time) تخسر أكثر — ارفع min_strength في هذه الساعات فقط."
        )

    scalp = next((r for r in by_tier if r["name"] == "SCALP"), None)
    if scalp and scalp["stats"]["total"] >= 5:
        sl_count = sum(1 for t in trades if t.trade_tier == "SCALP" and "stop" in t.close_reason.lower())
        if sl_count / max(scalp["stats"]["total"], 1) > 0.55:
            recs.append(
                "كثرة إغلاق SL في السكالبينغ — فعّل breakeven أسرع أو ارفع `SCALPING_MIN_RR` إلى 1.12."
            )

    if len(recs) < 5:
        recs.append(
            "فعّل `ML_FILTER_MODE=advisory` ثم enforce بعد أسبوع — يفلتر صفقات تشبه الخاسرة (لا تطبّق الآن)."
        )
    return recs[:5]


def _verdict(stats: dict) -> str:
    if stats["total"] < 3:
        return "عينة صغيرة — راقب"
    if stats["net_profit"] < 0:
        return "إيقاف/تخفيف"
    if stats.get("win_rate") and stats["win_rate"] < 0.35:
        return "تخفيف"
    return "إبقاء"


def build_report(since: datetime | None = None) -> str:
    since = since or since_midnight_utc()
    settings = get_settings()
    server_now = prop_server_now()

    db_rows: list[dict] = []
    pool = _pg_pool()
    if pool:
        try:
            db_rows = _fetch_db_outcomes(pool, since)
        except Exception as e:
            db_err = str(e)
        else:
            db_err = ""
    else:
        from tools import memory
        db_rows = [
            o for o in (memory.get_recent_outcomes(limit=500) or [])
            if (o.get("ts") or "") >= since.isoformat()
        ]
        db_err = "no postgres — using memory fallback"

    bridge_rows = _fetch_bridge_closed(since)
    trades = _merge_trades(db_rows, bridge_rows)

    lines: list[str] = []
    lines.append("# V11 Trade Review Report")
    lines.append("")
    lines.append(f"**Profile:** {getattr(settings, 'trading_mode_profile', 'N/A')}")
    lines.append(f"**Window:** server midnight → now")
    lines.append(f"**Server now:** {server_now.strftime('%Y-%m-%d %H:%M')} (UTC+{getattr(settings, 'prop_server_utc_offset_hours', 3)})")
    lines.append(f"**UTC since:** `{since.isoformat()}`")
    lines.append(f"**DB outcomes:** {len(db_rows)} | **MT5 bridge closed:** {len(bridge_rows)} | **Merged trades:** {len(trades)}")
    if db_err:
        lines.append(f"**DB note:** {db_err}")
    lines.append("")
    lines.append("> **لا تطبّق أي تعديل على `.env` قبل مراجعة ChatGPT.**")
    lines.append("")

    if len(trades) < len(bridge_rows) + len(db_rows) // 2:
        lines.append(
            "⚠️ **بيانات الاستراتيجية/النوع:** الصفقات القديمة قد لا تحتوي `strategy`/`trade_tier` "
            "— تم تحديث `close_logger` لتسجيلها للصفقات الجديدة. التقرير يستنتج من hold time عند الغياب."
        )
        lines.append("")

    s = _summary(trades)
    lines.append("## 1. ملخص عام")
    lines.append("")
    lines.append("| Metric | Value |")
    lines.append("|--------|-------|")
    for k, v in s.items():
        lines.append(f"| {k} | {v} |")
    lines.append("")

    by_tier = _group_stats(trades, lambda t: t.trade_tier)
    lines.append("## 2. حسب نوع الصفقة (scalping / intraday / swing)")
    lines.append("")
    for row in by_tier:
        st = row["stats"]
        lines.append(f"### {row['name']}")
        lines.append(f"- Trades: {st['total']} | Wins: {st['wins']} | Losses: {st['losses']}")
        lines.append(f"- Gross +: ${st['gross_profit']} | Gross -: ${st['gross_loss']} | Net: ${st['net_profit']}")
        lines.append(f"- Win rate: {st['win_rate']} | Avg hold (min): {row['avg_hold_min']}")
        if row["top_loss_reasons"]:
            lines.append(f"- Top loss reasons: {row['top_loss_reasons']}")
        lines.append("")

    by_strat = _group_stats(trades, lambda t: t.strategy)
    lines.append("## 3. حسب الاستراتيجية")
    lines.append("")
    lines.append("| Strategy | Trades | W | L | Net $ | Win% | Verdict |")
    lines.append("|----------|--------|---|---|-------|------|---------|")
    for row in by_strat:
        st = row["stats"]
        lines.append(
            f"| {row['name']} | {st['total']} | {st['wins']} | {st['losses']} "
            f"| {st['net_profit']} | {st['win_rate']} | {_verdict(st)} |"
        )
    lines.append("")

    by_sym = _group_stats(trades, lambda t: t.symbol)
    lines.append("## 4. حسب الرمز")
    lines.append("")
    lines.append("| Symbol | Trades | Net $ | Win% | Avg spread | Useful? |")
    lines.append("|--------|--------|-------|------|------------|---------|")
    for row in by_sym:
        st = row["stats"]
        spreads = [t.spread_pips for t in trades if t.symbol == row["name"] and t.spread_pips]
        avg_sp = round(sum(spreads) / len(spreads), 2) if spreads else "n/a"
        useful = "✅" if st["net_profit"] > 0 else ("⚠️" if st["net_profit"] == 0 else "❌")
        lines.append(
            f"| {row['name']} | {st['total']} | {st['net_profit']} | {st['win_rate']} | {avg_sp} | {useful} |"
        )
    lines.append("")

    by_time = _group_stats(trades, lambda t: _time_bucket(t.closed_at))
    lines.append("## 5. حسب الوقت (server time)")
    lines.append("")
    lines.append("| Period | Trades | Net $ | Win% |")
    lines.append("|--------|--------|-------|------|")
    for row in by_time:
        st = row["stats"]
        lines.append(f"| {row['name']} | {st['total']} | {st['net_profit']} | {st['win_rate']} |")
    lines.append("")

    losses = sorted(trades, key=lambda t: t.pnl)[:10]
    lines.append("## 6. أكبر 10 صفقات خاسرة")
    lines.append("")
    for t in losses:
        lines.append(f"### {t.symbol} {t.side} | PnL ${t.pnl}")
        lines.append(f"- Entry: {t.opened_at} | Exit: {t.closed_at} | Hold min: {t.hold_minutes}")
        lines.append(f"- Strategy: {t.strategy} | Tier: {t.trade_tier}")
        lines.append(f"- Close: {t.close_reason} | Spread: {t.spread_pips or 'n/a'}")
        lines.append(f"- SL/TP: {t.stop_loss} / {t.take_profit}")
        lines.append(f"- Strength: {t.strength or 'n/a'} | Skeptic hint: {t.skeptic_would_veto}")
        lines.append(f"- Natural loss or preventable: *review with ChatGPT*")
        lines.append("")

    wins = sorted(trades, key=lambda t: t.pnl, reverse=True)[:10]
    lines.append("## 7. أكبر 10 صفقات رابحة")
    lines.append("")
    for t in wins:
        lines.append(
            f"- **{t.symbol}** {t.side} +${t.pnl} | {t.strategy} | {t.close_reason} "
            f"| hold {t.hold_minutes}m"
        )
    lines.append("")

    lines.append("## 8. توصيات عملية (5 فقط — لا تطبّق تلقائيًا)")
    lines.append("")
    for i, rec in enumerate(_recommendations(trades, by_sym, by_strat, by_time, by_tier), 1):
        lines.append(f"{i}. {rec}")
    lines.append("")

    lines.append("## 9. أسئلة لـ ChatGPT")
    lines.append("")
    lines.append("- هل الخسائر من السكالبينغ أم intraday؟")
    lines.append("- أي رموز/استراتيجيات/ساعات نوقف أو نخفف؟")
    lines.append("- هل profit factor يبرر كثرة الخسائر الصغيرة؟")
    lines.append("- هل نرفع strength أم نفعّل ML filter أولًا؟")
    lines.append("")

    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("-o", "--output", default="V11_TRADE_REVIEW_REPORT.md")
    args = parser.parse_args()
    text = build_report()
    with open(args.output, "w", encoding="utf-8") as f:
        f.write(text)
    print(f"Wrote {args.output}")


if __name__ == "__main__":
    main()
