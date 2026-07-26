"""Phase 5B — active position management (time exit, breakeven, trailing)."""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from agents.risk_agent import pip_size_for
from config import get_settings
from tools import account_state, memory, mt5_bridge
from tools.session_engine import get_profile

logger = logging.getLogger("matrix.position_manager")


def _parse_ts(raw: str | None) -> datetime | None:
    if not raw:
        return None
    try:
        ts = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        return ts
    except Exception:
        return None


def _age_hours(pos: dict) -> float:
    ts = _parse_ts(pos.get("opened_at"))
    if not ts:
        return 0.0
    return max(0.0, (datetime.now(timezone.utc) - ts).total_seconds() / 3600.0)


def _risk_distance(pos: dict) -> float:
    entry = float(pos.get("entry_price") or pos.get("open_price") or 0)
    initial_sl = float(
        pos.get("initial_stop_loss")
        or pos.get("stop_loss")
        or pos.get("sl")
        or 0
    )
    if entry <= 0 or initial_sl <= 0:
        return 0.0
    return abs(entry - initial_sl)


def _favorable_move(pos: dict, current: float) -> float:
    entry = float(pos.get("entry_price") or pos.get("open_price") or 0)
    if entry <= 0 or current <= 0:
        return 0.0
    action = str(pos.get("action") or pos.get("type") or "BUY").upper()
    if action == "BUY":
        return max(0.0, current - entry)
    return max(0.0, entry - current)


def _r_multiple(pos: dict, current: float) -> float:
    risk = _risk_distance(pos)
    if risk <= 0:
        return 0.0
    return _favorable_move(pos, current) / risk


def _should_session_end_exit(settings, session: dict) -> bool:
    if not getattr(settings, "phase5_session_end_exit", True):
        return False
    return session.get("liquidity") == "low" and session.get("enabled")


def _new_sl_tp(
    pos: dict,
    current: float,
    settings,
    *,
    breakeven: bool,
    trail: bool,
) -> tuple[float | None, float | None]:
    entry = float(pos.get("entry_price") or pos.get("open_price") or 0)
    sl = float(pos.get("stop_loss") or pos.get("sl") or 0)
    tp = float(pos.get("take_profit") or pos.get("tp") or 0)
    action = str(pos.get("action") or pos.get("type") or "BUY").upper()
    pip = pip_size_for(pos.get("symbol", ""))
    buf = pip * 2  # 2-pip buffer beyond entry

    new_sl = sl
    if breakeven and entry > 0:
        if action == "BUY":
            be = entry - buf
            if sl <= 0 or be > sl:
                new_sl = round(be, 5)
        else:
            be = entry + buf
            if sl <= 0 or be < sl:
                new_sl = round(be, 5)

    if trail and entry > 0:
        risk = _risk_distance(pos)
        lock_r = float(getattr(settings, "phase5_trail_lock_r", 0.5))
        lock_dist = risk * lock_r
        if action == "BUY":
            trail_sl = entry + lock_dist
            if trail_sl > new_sl:
                new_sl = round(trail_sl, 5)
        else:
            # SELL: trail SL downward (lower price) as profit grows
            trail_sl = entry - lock_dist
            if sl <= 0 or trail_sl < new_sl:
                new_sl = round(trail_sl, 5)

    if new_sl != sl and new_sl > 0:
        return new_sl, tp if tp > 0 else None
    return None, None


async def manage_open_positions(
    mode: str,
    *,
    bridge_url: str | None = None,
    account_id: str = "primary",
    settings=None,
) -> dict[str, Any]:
    """Run position-management rules on all open positions."""
    settings = settings or get_settings()
    session = get_profile(settings)
    actions: list[dict] = []

    if not getattr(settings, "phase5_position_manager_enabled", True):
        return {"actions": [], "session": session, "skipped": "position manager disabled"}

    pos_key = "open_positions" if account_id == "primary" else f"open_positions__{account_id}"
    positions = memory.retrieve(pos_key) or []
    if mode == "ACTIVE":
        positions = await account_state.sync_open_positions(
            account_id=None if account_id == "primary" else account_id,
            bridge_url=bridge_url,
        ) or positions

    max_hold = float(getattr(settings, "phase5_max_hold_hours", 8.0))
    be_r = float(getattr(settings, "phase5_breakeven_at_r", 1.0))
    trail_r = float(getattr(settings, "phase5_trail_start_r", 1.5))
    min_hold = int(getattr(settings, "min_position_hold_seconds", 60))

    for pos in positions:
        tid = str(pos.get("trade_id") or pos.get("ticket") or "")
        sym = pos.get("symbol", "")
        current = float(pos.get("current_price") or pos.get("price_current") or 0)
        if current <= 0:
            entry = float(pos.get("entry_price") or pos.get("open_price") or 0)
            current = entry

        age_h = _age_hours(pos)
        r_mult = _r_multiple(pos, current)
        age_s = age_h * 3600.0

        # ── Max hold time exit ────────────────────────────────────────
        if age_h >= max_hold and age_s >= min_hold:
            if mode == "ACTIVE" and tid:
                res = await mt5_bridge.close_trade(tid, mode, bridge_url=bridge_url)
                actions.append({
                    "action": "close", "trade_id": tid, "symbol": sym,
                    "reason": f"max_hold {max_hold:.0f}h", "result": res,
                })
            else:
                actions.append({
                    "action": "close_sim", "trade_id": tid, "symbol": sym,
                    "reason": f"max_hold {max_hold:.0f}h (paper)",
                })
            continue

        # ── Session-end exit (entering low liquidity) ─────────────────
        if _should_session_end_exit(settings, session) and age_h >= 1.0 and age_s >= min_hold:
            if mode == "ACTIVE" and tid:
                res = await mt5_bridge.close_trade(tid, mode, bridge_url=bridge_url)
                actions.append({
                    "action": "close", "trade_id": tid, "symbol": sym,
                    "reason": "session_end_low_liquidity", "result": res,
                })
            continue

        # ── Breakeven + trailing SL modify ────────────────────────────
        if age_s < min_hold:
            continue

        want_be = r_mult >= be_r
        want_trail = r_mult >= trail_r
        try:
            from tools.surgical_filters import xagusd_breakeven_required
            if xagusd_breakeven_required(sym, settings):
                want_be = r_mult >= min(be_r, 0.5)
        except Exception:
            pass
        new_sl, new_tp = _new_sl_tp(
            pos, current, settings, breakeven=want_be, trail=want_trail,
        )
        if new_sl is None:
            continue

        if mode == "ACTIVE" and tid:
            res = await mt5_bridge.modify_position(
                int(tid), new_sl, new_tp or float(pos.get("take_profit") or pos.get("tp") or 0),
                bridge_url=bridge_url,
            )
            reason = "breakeven" if want_be and not want_trail else "trail" if want_trail else "modify"
            actions.append({
                "action": "modify_sl", "trade_id": tid, "symbol": sym,
                "new_sl": new_sl, "reason": reason, "r_multiple": round(r_mult, 2),
                "result": res,
            })
            if res.get("success"):
                pos["stop_loss"] = new_sl
                if not pos.get("initial_stop_loss"):
                    pos["initial_stop_loss"] = float(
                        pos.get("stop_loss") or pos.get("sl") or new_sl
                    )

    if actions:
        memory.store(pos_key, positions, ttl_seconds=86400 * 7)
        logger.info("Position manager: %d action(s)", len(actions))

    return {"actions": actions, "session": session, "open_count": len(positions)}
