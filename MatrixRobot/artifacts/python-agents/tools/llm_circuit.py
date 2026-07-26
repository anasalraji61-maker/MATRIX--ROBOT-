"""Process-level circuit breaker for OpenRouter.

When OpenRouter returns 401/402 (auth/credits) we trip the breaker for a
cool-down so the rest of the cycle stops hammering a dead endpoint and
immediately uses OpenAI / Gemini / ensemble fallback instead.
"""

from __future__ import annotations

import time
import logging

logger = logging.getLogger("matrix.llm_circuit")

_TRIPPED_UNTIL = 0.0
_COOLDOWN_SECONDS = 30 * 60  # 30 min


def is_openrouter_available() -> bool:
    return time.time() >= _TRIPPED_UNTIL


def trip_openrouter(reason: str = "") -> None:
    global _TRIPPED_UNTIL
    _TRIPPED_UNTIL = time.time() + _COOLDOWN_SECONDS
    logger.warning(
        f"OpenRouter circuit OPEN for {_COOLDOWN_SECONDS//60} min — {reason}"
    )
    try:
        import asyncio
        from tools import telegram_alerts
        from config import get_settings
        if get_settings().has_telegram:
            asyncio.get_event_loop().create_task(
                telegram_alerts.alert_openrouter_circuit(reason)
            )
    except Exception:
        pass


def is_credit_or_auth_error(exc: BaseException) -> bool:
    status = getattr(exc, "status_code", None) or getattr(exc, "status", None)
    if status in (401, 402, 403):
        return True
    msg = str(exc).lower()
    return (
        "insufficient credits" in msg
        or "payment required" in msg
        or "402" in msg
        or "401" in msg
    )
