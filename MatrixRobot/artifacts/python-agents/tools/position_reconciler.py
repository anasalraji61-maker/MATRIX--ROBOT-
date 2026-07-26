"""Near-real-time MT5 position reconciliation.

Polls each configured bridge every N seconds in ACTIVE mode so ghost
positions (closed on MT5 but still in memory) cannot block margin caps.

Does NOT call any LLM — local HTTP to MT5 bridge only.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from typing import Any, Optional

from config import get_settings
from tools import accounts as accounts_mod, account_state, memory, prop_rules

logger = logging.getLogger("matrix.reconciler")

_task: Optional[asyncio.Task] = None
_running = False

_status: dict[str, Any] = {
    "running": False,
    "interval_seconds": 10,
    "last_sync_at": None,
    "last_error": None,
    "bridge_ok": True,
    "bridge_stale": False,
    "accounts": {},
    "ghost_positions_removed_total": 0,
    "external_positions_imported_total": 0,
    "last_closed_trade": None,
    "sync_count": 0,
}


def get_status() -> dict:
    return dict(_status)


async def reconcile_all(force: bool = False) -> dict:
    """Sync every account once. Returns aggregated status."""
    global _status
    settings = get_settings()
    from routes.trading import get_effective_mode
    import runtime_state

    mode = runtime_state.get_mode() or settings.trading_state
    if mode != "ACTIVE" and not force:
        _status["bridge_ok"] = True
        _status["bridge_stale"] = False
        return get_status()

    account_results: dict[str, Any] = {}
    any_ok = False
    ghost_total = 0
    external_total = 0
    last_err: str | None = None

    for acct in accounts_mod.load_accounts():
        if not acct.enabled:
            continue
        bridge = (acct.bridge_url or settings.mt5_bridge_url or "").rstrip("/")
        acct_id = acct.id if acct.id != "primary" else None
        try:
            result = await account_state.reconcile_account(
                account_id=acct_id,
                bridge_url=bridge or None,
            )
            account_results[acct.id] = result
            if result.get("bridge_ok"):
                any_ok = True
            ghost_total += int(result.get("ghost_removed", 0) or 0)
            external_total += int(result.get("external_imported", 0) or 0)
            if result.get("last_closed"):
                _status["last_closed_trade"] = result["last_closed"]
        except Exception as e:
            last_err = str(e)
            logger.warning(f"Reconcile failed for {acct.id}: {e}")
            account_results[acct.id] = {"bridge_ok": False, "error": str(e)}

    now = datetime.now(timezone.utc).isoformat()
    _status.update({
        "last_sync_at": now,
        "last_error": last_err,
        "bridge_ok": any_ok or not settings.mt5_bridge_url,
        "bridge_stale": bool(settings.mt5_bridge_url) and not any_ok,
        "accounts": account_results,
        "ghost_positions_removed_total": (
            int(_status.get("ghost_positions_removed_total", 0)) + ghost_total
        ),
        "external_positions_imported_total": (
            int(_status.get("external_positions_imported_total", 0)) + external_total
        ),
        "sync_count": int(_status.get("sync_count", 0)) + 1,
        "interval_seconds": int(settings.position_reconcile_interval_seconds),
    })
    if ghost_total:
        logger.info(f"Reconciler removed {ghost_total} ghost position(s)")
    try:
        from tools import account_health
        await account_health.maybe_alert_disabled_accounts()
    except Exception:
        pass
    return get_status()


async def ensure_synced() -> bool:
    """Hard sync before risk/execution. Returns True if bridge state is trusted."""
    settings = get_settings()
    if not (settings.mt5_bridge_url or "").strip():
        return True
    status = await reconcile_all(force=True)
    if status.get("bridge_stale"):
        return False
    return bool(status.get("bridge_ok", False))


async def _loop(interval: int):
    global _running
    logger.info(f"Position reconciler started — every {interval}s")
    while _running:
        try:
            await reconcile_all()
        except Exception as e:
            logger.exception(f"Reconciler loop error: {e}")
            _status["last_error"] = str(e)
        await asyncio.sleep(interval)
    logger.info("Position reconciler stopped")


def start_background():
    global _task, _running
    settings = get_settings()
    if _running:
        return
    interval = max(5, int(settings.position_reconcile_interval_seconds))
    _running = True
    _status["running"] = True
    _status["interval_seconds"] = interval
    _task = asyncio.create_task(_loop(interval))


async def stop_background():
    global _task, _running
    _running = False
    _status["running"] = False
    if _task and not _task.done():
        _task.cancel()
        try:
            await _task
        except asyncio.CancelledError:
            pass
    _task = None
