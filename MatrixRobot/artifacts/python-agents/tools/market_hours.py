"""
Market hours guard — forex session awareness.

The bot must NOT consume LLM credits or run analysis when the market is closed.
Per user requirement: pause Saturday + Sunday (UTC), resume Monday 00:00 UTC.

(Forex actually closes Fri 22:00 UTC → Sun 22:00 UTC, but the user-friendly
rule is "weekend off, back Monday midnight UTC" which we honor strictly.)
"""
from __future__ import annotations

from datetime import datetime, timezone, timedelta


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def is_market_closed(now: datetime | None = None) -> tuple[bool, str]:
    """Returns (closed, reason).

    Closed when UTC weekday is Saturday (5) or Sunday (6).
    Open Monday 00:00 UTC through Friday 23:59 UTC.
    """
    n = now or _now_utc()
    wd = n.weekday()  # 0=Mon, 5=Sat, 6=Sun
    if wd == 5:
        return True, "Market closed — Saturday (UTC). Resumes Monday 00:00 UTC."
    if wd == 6:
        return True, "Market closed — Sunday (UTC). Resumes Monday 00:00 UTC."
    return False, ""


def seconds_until_market_open(now: datetime | None = None) -> int:
    """Seconds until next Monday 00:00 UTC. Returns 0 if market is open."""
    n = now or _now_utc()
    closed, _ = is_market_closed(n)
    if not closed:
        return 0
    days_ahead = (7 - n.weekday()) % 7  # to reach next Monday
    if days_ahead == 0:
        days_ahead = 1  # safety
    monday = (n + timedelta(days=days_ahead)).replace(
        hour=0, minute=0, second=0, microsecond=0
    )
    return max(60, int((monday - n).total_seconds()))


def market_status(now: datetime | None = None) -> dict:
    """Snapshot for /agents/* responses."""
    n = now or _now_utc()
    closed, reason = is_market_closed(n)
    return {
        "is_open": not closed,
        "is_closed": closed,
        "reason": reason,
        "weekday": n.strftime("%A"),
        "utc_now": n.isoformat(),
        "seconds_until_open": seconds_until_market_open(n) if closed else 0,
    }
