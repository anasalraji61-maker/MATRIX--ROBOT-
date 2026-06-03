"""
Economic Calendar — light, fully internal version.

Why internal? Reliable free APIs (Forex Factory JSON, MyFXBook, etc.) keep
changing and often need scraping; we don't want a hard dependency on an
external HTML format. So we use a *recurring weekly schedule* of known
high-impact windows:

    Mon-Fri 12:30-13:30 UTC : US morning data (PPI, jobless claims, etc.)
    Wed     17:30-19:30 UTC : FOMC meeting / Fed statement window (when scheduled)
    Thu     11:45-13:00 UTC : ECB policy + press conference window
    Fri     12:30-13:30 UTC : NFP / US jobs data window

This is intentionally *conservative* — better to miss a few minutes of
trading than blow a prop-firm account on an NFP whipsaw. The user can
turn it off via `ECONOMIC_CALENDAR_ENABLED=false`.

`affected_currencies` lets the risk agent block only trades that involve
the currency in question, instead of freezing the whole book.
"""
from __future__ import annotations

from datetime import datetime, timezone, timedelta
from config import get_settings
from models.schemas import EconomicCalendar, EconomicEvent


# Each entry: (weekday 0=Mon, start_h, start_m, end_h, end_m, currencies, title, impact)
_WINDOWS: list[tuple] = [
    (0, 12, 30, 13, 30, ["USD"], "US data window (PPI/claims)", "MEDIUM"),
    (1, 12, 30, 13, 30, ["USD"], "US data window",              "MEDIUM"),
    (2, 12, 30, 13, 30, ["USD"], "US data window",              "MEDIUM"),
    (2, 17, 30, 19, 30, ["USD"], "FOMC / Fed window",           "HIGH"),
    (3, 11, 45, 13,  0, ["EUR"], "ECB policy window",           "HIGH"),
    (3, 12, 30, 13, 30, ["USD"], "US data window",              "MEDIUM"),
    (4, 12, 30, 13, 30, ["USD"], "NFP / US jobs data window",   "HIGH"),
]


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _today_window(now: datetime, w) -> tuple[datetime, datetime, list[str], str, str]:
    wd, sh, sm, eh, em, ccys, title, impact = w
    base = now - timedelta(days=now.weekday() - wd)
    start = base.replace(hour=sh, minute=sm, second=0, microsecond=0)
    end = base.replace(hour=eh, minute=em, second=0, microsecond=0)
    return start, end, ccys, title, impact


def get_calendar() -> EconomicCalendar:
    s = get_settings()
    if not s.economic_calendar_enabled:
        return EconomicCalendar(in_blackout=False, source="disabled")

    now = _now_utc()
    upcoming: list[EconomicEvent] = []
    affected: set[str] = set()
    in_blackout = False
    blackout_reason = ""

    # Check ±36h window for upcoming events and current blackout
    for w in _WINDOWS:
        for day_off in range(-1, 3):  # yesterday → +2 days
            wd = w[0]
            ccys = w[5]
            title = w[6]
            impact = w[7]
            # Compute the date that has weekday=wd within ±day_off-ish range
            day_base = now + timedelta(days=day_off)
            shift = (wd - day_base.weekday()) % 7
            target_day = day_base + timedelta(days=shift)
            start = target_day.replace(hour=w[1], minute=w[2], second=0, microsecond=0)
            end = target_day.replace(hour=w[3], minute=w[4], second=0, microsecond=0)

            # Currently inside this window?
            if start <= now <= end:
                in_blackout = True
                blackout_reason = f"{title} ({','.join(ccys)})"
                affected.update(ccys)

            # Upcoming within next 24h?
            if now < start <= now + timedelta(hours=24):
                upcoming.append(EconomicEvent(
                    title=title,
                    currency=",".join(ccys),
                    impact=impact,
                    when_iso=start.isoformat(),
                    minutes_until=int((start - now).total_seconds() / 60),
                ))

    # Pre-event buffer: also blackout N minutes BEFORE high-impact events
    buf = s.economic_calendar_pre_event_minutes
    if not in_blackout and buf > 0:
        for ev in upcoming:
            if ev.impact == "HIGH" and ev.minutes_until <= buf:
                in_blackout = True
                blackout_reason = f"pre-event buffer: {ev.title} in {ev.minutes_until}m"
                affected.update(ev.currency.split(","))
                break

    # Post-event buffer: also blackout N minutes AFTER high-impact events
    # (FN considers post-news re-entries as exploiting volatility spikes).
    # Re-scan recent windows that ENDED within last `post_buf` minutes.
    post_buf = s.economic_calendar_post_event_minutes
    if not in_blackout and post_buf > 0:
        for w in _WINDOWS:
            wd, sh, sm, eh, em, ccys, title, impact = w
            if impact != "HIGH":
                continue
            for day_off in range(-1, 2):
                day_base = now + timedelta(days=day_off)
                shift = (wd - day_base.weekday()) % 7
                target_day = day_base + timedelta(days=shift)
                end = target_day.replace(hour=eh, minute=em, second=0, microsecond=0)
                mins_since = (now - end).total_seconds() / 60.0
                if 0 < mins_since <= post_buf:
                    in_blackout = True
                    blackout_reason = (
                        f"post-event buffer: {title} ended {int(mins_since)}m ago "
                        f"(wait {int(post_buf - mins_since)}m more)"
                    )
                    affected.update(ccys)
                    break
            if in_blackout:
                break

    # De-dupe upcoming by (title, when_iso)
    seen = set()
    deduped: list[EconomicEvent] = []
    for ev in sorted(upcoming, key=lambda e: e.when_iso):
        key = (ev.title, ev.when_iso)
        if key in seen:
            continue
        seen.add(key)
        deduped.append(ev)

    return EconomicCalendar(
        in_blackout=in_blackout,
        blackout_reason=blackout_reason,
        affected_currencies=sorted(affected),
        upcoming=deduped[:10],
        source="internal-weekly",
    )


def symbol_affected(symbol: str, affected_currencies: list[str]) -> bool:
    """True if the symbol contains any of the affected currencies."""
    if not affected_currencies:
        return False
    s = symbol.upper()
    return any(ccy.upper() in s for ccy in affected_currencies)
