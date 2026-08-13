"""Bridge manual-check state — unresolved position tickets after open."""
from __future__ import annotations

import logging
from datetime import datetime, timezone

from config import get_settings
from tools import memory

logger = logging.getLogger("matrix.bridge_manual")

_BLOCK_KEY = "bridge_manual_check_active"
_DETAIL_KEY = "bridge_manual_check_required"
# No TTL — persists until admin clears via POST /circuit/clear-manual-check
_PERSIST_TTL = 0

MANUAL_CHECK_CLEAR_PHRASE = (
    "I confirm I checked MT5 manually and no unmanaged position exists."
)


def is_blocking() -> bool:
    return memory.retrieve(_DETAIL_KEY) is not None


def get_status() -> dict | None:
    if not is_blocking():
        return None
    detail = memory.retrieve(_DETAIL_KEY) or {}
    return {"active": True, **detail}


async def record_manual_check_required(symbol: str, data: dict) -> dict:
    """Persist flag, log CRITICAL, send Telegram. Blocks new trades until cleared."""
    rec = {
        "symbol": symbol,
        "order_id": data.get("order_id"),
        "comment": data.get("comment", ""),
        "recorded_at": datetime.now(timezone.utc).isoformat(),
    }
    memory.store(_DETAIL_KEY, rec, ttl_seconds=_PERSIST_TTL)
    memory.store(_BLOCK_KEY, True, ttl_seconds=_PERSIST_TTL)
    logger.critical(
        "MANUAL CHECK REQUIRED: %s order_id=%s — position may be open without known ticket",
        symbol, rec.get("order_id"),
    )
    settings = get_settings()
    try:
        from tools import telegram_alerts
        if settings.has_telegram:
            await telegram_alerts.alert_manual_check_required(symbol, rec)
    except Exception:
        pass
    return rec


def clear() -> None:
    memory.store(_BLOCK_KEY, False, ttl_seconds=_PERSIST_TTL)
    memory.store(_DETAIL_KEY, None, ttl_seconds=_PERSIST_TTL)
