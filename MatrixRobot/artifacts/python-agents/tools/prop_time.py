"""FundedNext / broker server calendar time.

Daily P&L reset follows **00:00 broker server time** (GMT+2/+3), not UTC.
Configure offset via PROP_SERVER_UTC_OFFSET_HOURS (default 3).
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from config import get_settings


def prop_server_now() -> datetime:
    s = get_settings()
    off = int(getattr(s, "prop_server_utc_offset_hours", 3))
    return datetime.now(timezone.utc) + timedelta(hours=off)


def prop_server_today() -> str:
    return prop_server_now().strftime("%Y-%m-%d")


def seconds_until_prop_server_midnight() -> int:
    now = prop_server_now()
    tomorrow = (now + timedelta(days=1)).replace(
        hour=0, minute=0, second=0, microsecond=0,
    )
    return max(60, int((tomorrow - now).total_seconds()))


def today_key() -> str:
    return prop_server_today()
