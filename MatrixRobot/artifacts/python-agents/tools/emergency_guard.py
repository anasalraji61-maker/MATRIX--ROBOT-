"""
Emergency portfolio guard — circuit breaker that fires BEFORE the cycle pipeline.

Two protections the gatekeeper-style risk_agent doesn't provide:

  1) **Emergency liquidation** — if floating-equity daily DD breaches the soft
     cap (default 3.5%), close every open position immediately via MT5 bridge.
     This catches situations where positions opened at safe size drift against
     the account in aggregate and bleed past the daily cap.

  2) **Daily lockout** — once the hard internal cap (default 4%) is hit, mark
     today as LOCKED. No analysis, no risk, no execution runs for the rest of
     the UTC day. Auto-resets at 00:00 UTC the next day.

This module is intentionally side-effect light: the only mutation it performs
is calling the MT5 bridge `/trade/close` endpoint and writing a single flag
into the memory layer. Everything else is reading.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone, timedelta
from typing import Optional

import httpx

from config import get_settings
from tools import memory, account_state, market_hours

logger = logging.getLogger("matrix.emergency_guard")

_LOCKOUT_KEY = "prop_daily_lockout"


# ---------- lockout state ----------------------------------------------------

def _today_utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def _seconds_until_utc_midnight() -> int:
    now = datetime.now(timezone.utc)
    tomorrow = (now + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
    return max(60, int((tomorrow - now).total_seconds()))


def get_lockout() -> dict:
    """Returns lockout record for today, or {} if not locked."""
    rec = memory.retrieve(_LOCKOUT_KEY) or {}
    if rec.get("date") != _today_utc():
        return {}
    return dict(rec)


def is_daily_locked() -> bool:
    return bool(get_lockout())


def set_daily_lockout(reason: str, daily_dd_pct: float, floating_pnl: float) -> dict:
    rec = {
        "date": _today_utc(),
        "reason": reason,
        "daily_dd_pct": round(daily_dd_pct, 3),
        "floating_pnl": round(floating_pnl, 2),
        "locked_at": datetime.now(timezone.utc).isoformat(),
        "unlocks_at": (
            datetime.now(timezone.utc) + timedelta(seconds=_seconds_until_utc_midnight())
        ).isoformat(),
    }
    memory.store(_LOCKOUT_KEY, rec, ttl_seconds=_seconds_until_utc_midnight() + 120)
    logger.error(
        "DAILY LOCKOUT TRIPPED: %s | dd=%.2f%% | floating=%.2f EUR | unlocks at UTC midnight",
        reason, daily_dd_pct, floating_pnl,
    )
    return rec


def clear_lockout() -> None:
    """Manual override (used by reset_for_new_challenge or admin endpoint)."""
    memory.delete(_LOCKOUT_KEY) if hasattr(memory, "delete") else memory.store(_LOCKOUT_KEY, {}, ttl_seconds=10)


# ---------- bridge calls -----------------------------------------------------

async def _fetch_bridge_positions(settings) -> list[dict]:
    if not settings.mt5_bridge_url:
        return []
    headers = {}
    if getattr(settings, "mt5_bridge_secret", ""):
        headers["X-Bridge-Secret"] = settings.mt5_bridge_secret
    try:
        async with httpx.AsyncClient(timeout=8.0) as client:
            r = await client.get(f"{settings.mt5_bridge_url}/positions", headers=headers)
            r.raise_for_status()
            data = r.json()
            return data.get("positions", []) if isinstance(data, dict) else (data or [])
    except Exception as e:
        logger.warning("emergency_guard: failed to fetch bridge positions: %s", e)
        return []


async def _close_position_via_bridge(settings, trade_id: str | int) -> dict:
    if not settings.mt5_bridge_url:
        return {"success": False, "error": "no bridge"}
    headers = {"Content-Type": "application/json"}
    if getattr(settings, "mt5_bridge_secret", ""):
        headers["X-Bridge-Secret"] = settings.mt5_bridge_secret
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            r = await client.post(
                f"{settings.mt5_bridge_url}/trade/close",
                headers=headers,
                json={"trade_id": int(trade_id), "comment": "matrix-emergency-liquidation"},
            )
            r.raise_for_status()
            return {"success": True, "trade_id": trade_id, "result": r.json()}
    except Exception as e:
        return {"success": False, "trade_id": trade_id, "error": str(e)}


async def liquidate_all_positions(settings) -> dict:
    """Closes every open MT5 position. Returns a per-trade result dict."""
    positions = await _fetch_bridge_positions(settings)
    if not positions:
        return {"closed": 0, "results": [], "reason": "no_open_positions"}
    results = []
    for p in positions:
        tid = p.get("trade_id") or p.get("ticket")
        if tid is None:
            continue
        res = await _close_position_via_bridge(settings, tid)
        results.append({**res, "symbol": p.get("symbol"), "profit": p.get("profit")})
    closed = sum(1 for r in results if r.get("success"))
    logger.warning("emergency_liquidation: closed %d/%d positions", closed, len(results))
    return {"closed": closed, "attempted": len(results), "results": results}


# ---------- main entry -------------------------------------------------------

async def evaluate(state: dict | None = None) -> dict:
    """
    Returns a dict describing whether the cycle should proceed:
      {
        "locked": bool,                 # if True, skip the whole cycle
        "tripped_now": bool,            # if True, lockout was just set this call
        "liquidated": dict | None,      # liquidation result if executed this call
        "lockout": dict,                # the lockout record (if locked)
        "soft_breach": bool,            # exceeded soft cap (warn, no action)
        "daily_dd_pct": float,
        "floating_pnl": float,
        "thresholds": { soft, hard, fn_cap },
      }

    Side effects: may CLOSE all positions and SET the daily lockout flag.
    """
    settings = get_settings()
    soft_cap = float(getattr(settings, "emergency_soft_cap_pct", 3.5))
    hard_cap = float(getattr(settings, "max_daily_drawdown_pct", 4.0))
    fn_cap   = float(getattr(settings, "fn_max_daily_loss_pct", 5.0))

    # Market hours guard — skip the whole cycle (and LLM cost) when forex is closed
    mkt = market_hours.market_status()
    if mkt["is_closed"]:
        logger.info("market closed: %s", mkt["reason"])
        return {
            "locked": True, "tripped_now": False, "liquidated": None,
            "lockout": {
                "reason": mkt["reason"],
                "kind": "market_closed",
                "weekday": mkt["weekday"],
                "seconds_until_open": mkt["seconds_until_open"],
            },
            "soft_breach": False,
            "daily_dd_pct": 0.0, "floating_pnl": 0.0,
            "thresholds": {"soft": soft_cap, "hard": hard_cap, "fn_cap": fn_cap},
            "market": mkt,
        }

    # Already locked for today → block the cycle straight away
    if is_daily_locked():
        return {
            "locked": True, "tripped_now": False, "liquidated": None,
            "lockout": get_lockout(), "soft_breach": True,
            "daily_dd_pct": float(get_lockout().get("daily_dd_pct", 0.0)),
            "floating_pnl": float(get_lockout().get("floating_pnl", 0.0)),
            "thresholds": {"soft": soft_cap, "hard": hard_cap, "fn_cap": fn_cap},
        }

    # Compute current floating-equity daily DD
    snap = await account_state.refresh_account()
    if not snap or not snap.get("available"):
        # Can't read account — fail open (don't block) but log
        logger.warning("emergency_guard: account snapshot unavailable, skipping check")
        return {
            "locked": False, "tripped_now": False, "liquidated": None,
            "lockout": {}, "soft_breach": False,
            "daily_dd_pct": 0.0, "floating_pnl": 0.0,
            "thresholds": {"soft": soft_cap, "hard": hard_cap, "fn_cap": fn_cap},
        }

    daily_dd = float(snap.get("daily_drawdown_pct", 0.0))
    equity   = float(snap.get("equity", 0.0))
    balance  = float(snap.get("balance", 0.0))
    floating = equity - balance  # floating P&L

    soft_breach = daily_dd >= soft_cap
    hard_breach = daily_dd >= hard_cap

    if not soft_breach:
        return {
            "locked": False, "tripped_now": False, "liquidated": None,
            "lockout": {}, "soft_breach": False,
            "daily_dd_pct": daily_dd, "floating_pnl": floating,
            "thresholds": {"soft": soft_cap, "hard": hard_cap, "fn_cap": fn_cap},
        }

    # SOFT BREACH: liquidate all positions now to stop the bleeding.
    # HARD BREACH: also lock the day so no further trading happens until UTC midnight.
    logger.warning(
        "EMERGENCY GUARD breach: daily_dd=%.2f%% (soft=%.1f, hard=%.1f, fn_cap=%.1f) floating=%.2f",
        daily_dd, soft_cap, hard_cap, fn_cap, floating,
    )
    liquidation = await liquidate_all_positions(settings)

    lockout_rec = {}
    tripped_now = False
    if hard_breach:
        lockout_rec = set_daily_lockout(
            reason=f"Daily DD {daily_dd:.2f}% >= hard cap {hard_cap:.1f}% — auto liquidated",
            daily_dd_pct=daily_dd,
            floating_pnl=floating,
        )
        tripped_now = True

    return {
        "locked": bool(lockout_rec),
        "tripped_now": tripped_now,
        "liquidated": liquidation,
        "lockout": lockout_rec,
        "soft_breach": True,
        "daily_dd_pct": daily_dd,
        "floating_pnl": floating,
        "thresholds": {"soft": soft_cap, "hard": hard_cap, "fn_cap": fn_cap},
    }
