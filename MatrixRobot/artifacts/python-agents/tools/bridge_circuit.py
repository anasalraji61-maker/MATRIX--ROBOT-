"""Circuit breaker for MT5 HTTP bridges — stop retry loops, alert via Telegram."""
from __future__ import annotations

import logging
import time

logger = logging.getLogger("matrix.bridge_circuit")

_FAILURES: dict[str, int] = {}
_OPEN_UNTIL: dict[str, float] = {}
_TRIP_THRESHOLD = 2
_COOLDOWN_SECONDS = 300  # 5 min


_open_alerted_at: dict[str, float] = {}


def is_open(bridge_url: str) -> bool:
    url = (bridge_url or "").rstrip("/")
    if not url:
        return False
    until = _OPEN_UNTIL.get(url, 0.0)
    if time.time() < until:
        return True
    if until > 0:
        _OPEN_UNTIL.pop(url, None)
        _FAILURES.pop(url, None)
    return False


def should_alert(bridge_url: str) -> bool:
    """Telegram at most once per cooldown per bridge URL."""
    url = (bridge_url or "").rstrip("/")
    if not url:
        return False
    last = _open_alerted_at.get(url, 0.0)
    if time.time() - last < _COOLDOWN_SECONDS:
        return False
    _open_alerted_at[url] = time.time()
    return True


def record_success(bridge_url: str) -> None:
    url = (bridge_url or "").rstrip("/")
    if url:
        _FAILURES.pop(url, None)
        _OPEN_UNTIL.pop(url, None)


def record_failure(bridge_url: str, reason: str = "") -> bool:
    """Increment failures. Returns True if circuit just tripped."""
    url = (bridge_url or "").rstrip("/")
    if not url:
        return False
    count = _FAILURES.get(url, 0) + 1
    _FAILURES[url] = count
    if count >= _TRIP_THRESHOLD:
        _OPEN_UNTIL[url] = time.time() + _COOLDOWN_SECONDS
        logger.warning("Bridge circuit OPEN for %s (%s)", url, reason)
        return True
    return False


def status(bridge_url: str) -> dict:
    url = (bridge_url or "").rstrip("/")
    return {
        "url": url,
        "open": is_open(url),
        "failures": _FAILURES.get(url, 0),
        "open_until": _OPEN_UNTIL.get(url),
    }
