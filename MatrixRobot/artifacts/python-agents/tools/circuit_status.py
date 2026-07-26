"""Phase 1.4 — unified circuit breaker status + cycle preflight."""
from __future__ import annotations

import logging
from datetime import datetime, timezone

import httpx

from config import get_settings
from tools import bridge_circuit, emergency_guard, llm_circuit, memory, position_reconciler

logger = logging.getLogger("matrix.circuit_status")


async def _ping_bridge(bridge_url: str) -> bool:
    settings = get_settings()
    url = bridge_url.rstrip("/")
    headers = {}
    secret = settings.mt5_bridge_secret or ""
    if secret:
        headers["X-Bridge-Secret"] = secret
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            r = await client.get(f"{url}/version", headers=headers)
            return r.status_code == 200
    except Exception:
        return False


def _bridge_block_reason(mode: str) -> tuple[bool, str, dict]:
    """Returns (blocked, reason_code, bridge_info)."""
    settings = get_settings()
    url = (settings.mt5_bridge_url or "").rstrip("/")
    info = {
        "url": url or None,
        "circuit_open": False,
        "reachable": None,
        "required": mode == "ACTIVE" and bool(url),
    }
    if mode != "ACTIVE" or not url:
        return False, "", info

    if bridge_circuit.is_open(url):
        info["circuit_open"] = True
        return True, "bridge_circuit_open", info

    st = bridge_circuit.status(url)
    info.update(st)
    return False, "", info


async def preflight_cycle(mode: str) -> dict:
    """
    Gate before LangGraph — skip expensive LLM when trading infra is down.
    Returns {can_run, reason, message, bridge, ...}.
    """
    settings = get_settings()
    blocked, code, bridge_info = _bridge_block_reason(mode)

    if blocked:
        return {
            "can_run": False,
            "reason": code,
            "message": "Trading paused — MT5 bridge circuit is OPEN",
            "bridge": bridge_info,
        }

    lockout = emergency_guard.get_lockout()
    manual_check = None
    try:
        from tools.bridge_manual import get_status
        manual_check = get_status()
    except Exception:
        pass

    if lockout:
        return {
            "can_run": False,
            "reason": "daily_lockout",
            "message": lockout.get("reason", "Daily lockout active"),
            "lockout": lockout,
            "bridge": bridge_info,
        }

    if manual_check and mode == "ACTIVE":
        return {
            "can_run": False,
            "reason": "bridge_manual_check",
            "message": "Trading paused — unresolved MT5 position ticket; manual check required",
            "bridge": bridge_info,
            "manual_check": manual_check,
        }

    if mode == "ACTIVE" and bridge_info.get("required"):
        url = bridge_info["url"]
        reachable = await _ping_bridge(url)
        bridge_info["reachable"] = reachable
        if not reachable:
            tripped = bridge_circuit.record_failure(url, "preflight ping failed")
            if tripped and bridge_circuit.should_alert(url):
                try:
                    from tools import telegram_alerts
                    if settings.has_telegram:
                        await telegram_alerts.alert_bridge_open(
                            url, "Bridge unreachable at cycle preflight",
                        )
                except Exception:
                    pass
            return {
                "can_run": False,
                "reason": "bridge_unreachable",
                "message": "Trading paused — MT5 bridge unreachable",
                "bridge": bridge_info,
            }
        bridge_circuit.record_success(url)

        sync_ok = await position_reconciler.ensure_synced()
        bridge_info["reconciled"] = sync_ok
        if not sync_ok:
            return {
                "can_run": False,
                "reason": "bridge_stale",
                "message": "Trading paused — could not sync MT5 positions",
                "bridge": bridge_info,
            }

    if mode == "ACTIVE" and getattr(settings, "active_require_persistent_state", True):
        if not memory.has_persistent_backend():
            return {
                "can_run": False,
                "reason": "no_persistent_state",
                "message": "Trading paused — ACTIVE requires Postgres or Redis (in-memory fallback disabled)",
                "bridge": bridge_info,
            }

    llm_ok = bool(settings.has_llm)
    if settings.effective_openrouter_key and not llm_circuit.is_openrouter_available():
        llm_ok = bool(settings.effective_openai_key or settings.effective_gemini_key)

    return {
        "can_run": True,
        "reason": "",
        "message": "OK",
        "bridge": bridge_info,
        "llm_available": llm_ok,
        "openrouter_circuit_open": bool(
            settings.effective_openrouter_key
            and not llm_circuit.is_openrouter_available()
        ),
    }


async def full_report() -> dict:
    """Dashboard / API snapshot of all breakers."""
    settings = get_settings()
    from routes.trading import get_effective_mode

    mode = get_effective_mode()
    url = (settings.mt5_bridge_url or "").rstrip("/")
    bridge_st = bridge_circuit.status(url) if url else {"url": None, "open": False}

    reachable = None
    if url:
        reachable = await _ping_bridge(url)
        bridge_st["reachable"] = reachable

    reconciler = position_reconciler.get_status()
    lockout = emergency_guard.get_lockout()
    try:
        from tools.bridge_manual import get_status as _manual_status
        manual_check = _manual_status()
    except Exception:
        manual_check = None
    preflight = await preflight_cycle(mode)

    return {
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "mode": mode,
        "can_trade": preflight["can_run"] and mode == "ACTIVE",
        "preflight": preflight,
        "bridge": bridge_st,
        "reconciler": {
            "running": reconciler.get("running"),
            "bridge_ok": reconciler.get("bridge_ok"),
            "bridge_stale": reconciler.get("bridge_stale"),
            "last_sync_at": reconciler.get("last_sync_at"),
            "last_error": reconciler.get("last_error"),
        },
        "llm": {
            "openrouter_configured": bool(settings.effective_openrouter_key),
            "openrouter_circuit_open": bool(
                settings.effective_openrouter_key
                and not llm_circuit.is_openrouter_available()
            ),
            "has_fallback_llm": bool(
                settings.effective_openai_key or settings.effective_gemini_key
            ),
        },
        "daily_lockout": lockout or None,
        "emergency_locked": bool(lockout),
        "manual_check": manual_check if manual_check else None,
    }
