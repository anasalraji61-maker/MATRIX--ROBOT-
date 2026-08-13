"""Daily health ping for disabled accounts — one Telegram per 24h max."""
from __future__ import annotations

import logging
from datetime import datetime, timezone

from config import get_settings
from tools import accounts as accounts_mod, memory, mt5_bridge

logger = logging.getLogger("matrix.account_health")

_ALERT_INTERVAL_S = 86400  # 24 hours
_MEM_PREFIX = "disabled_bridge_alert__"


def _last_alert_ts(account_id: str) -> float:
    raw = memory.retrieve(f"{_MEM_PREFIX}{account_id}")
    try:
        return float(raw or 0)
    except (TypeError, ValueError):
        return 0.0


def _mark_alerted(account_id: str) -> None:
    memory.store(
        f"{_MEM_PREFIX}{account_id}",
        datetime.now(timezone.utc).timestamp(),
        ttl_seconds=_ALERT_INTERVAL_S * 2,
    )


async def maybe_alert_disabled_accounts() -> None:
    """Once per 24h per disabled account: report bridge up/down (no spam)."""
    settings = get_settings()
    if not settings.has_telegram:
        return

    now_ts = datetime.now(timezone.utc).timestamp()
    for acct in accounts_mod.load_accounts():
        if acct.enabled or not (acct.bridge_url or "").strip():
            continue
        if now_ts - _last_alert_ts(acct.id) < _ALERT_INTERVAL_S:
            continue

        bridge = acct.bridge_url.rstrip("/")
        online = False
        err = ""
        try:
            import httpx
            headers = {}
            secret = settings.mt5_bridge_secret or ""
            if secret:
                headers["X-Bridge-Secret"] = secret
            async with httpx.AsyncClient(timeout=5) as client:
                r = await client.get(f"{bridge}/version", headers=headers)
                online = r.status_code == 200
                if not online:
                    err = f"HTTP {r.status_code}"
        except Exception as e:
            err = str(e)[:120]

        _mark_alerted(acct.id)

        logger.info(
            "Daily disabled-account check %s bridge=%s online=%s",
            acct.id, bridge, online,
        )

        # Disabled + bridge offline is expected (ForexIraq / 5556 closed) — log only.
        if not online:
            continue

        try:
            from tools import telegram_alerts
            await telegram_alerts.send(
                f"Daily check [{acct.label}]\n"
                f"Account: DISABLED in .env (no trades)\n"
                f"Bridge {bridge}: ONLINE\n"
                f"Ready when you set enabled:true",
                level="info",
                disable_notification=True,
            )
        except Exception:
            logger.exception("Daily disabled-account alert failed for %s", acct.id)
