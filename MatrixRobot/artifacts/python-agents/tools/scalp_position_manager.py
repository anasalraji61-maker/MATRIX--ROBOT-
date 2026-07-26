"""V11 scalp position manager — max hold, breakeven, trailing."""
from __future__ import annotations

import logging
from datetime import datetime, timezone

from config import get_settings
from tools import memory

logger = logging.getLogger("matrix.scalp_position_manager")


def _parse_ts(ts: str | None) -> datetime | None:
    if not ts:
        return None
    try:
        return datetime.fromisoformat(ts.replace("Z", "+00:00"))
    except Exception:
        return None


async def manage_scalp_positions(state: dict) -> dict:
    """Close or adjust SCALP-tier positions past max hold."""
    settings = get_settings()
    if not getattr(settings, "scalping_enabled", False):
        return {"actions": [], "closed": 0}

    positions = list(memory.retrieve("open_positions") or [])
    if not positions:
        return {"actions": [], "closed": 0}

    max_hold = int(settings.scalping_max_hold_minutes)
    now = datetime.now(timezone.utc)
    actions: list[dict] = []
    closed = 0
    remaining: list[dict] = []

    for p in positions:
        tier = str(p.get("trade_tier") or "").upper()
        if tier != "SCALP":
            remaining.append(p)
            continue

        opened = _parse_ts(p.get("opened_at"))
        if opened and (now - opened).total_seconds() / 60 > max_hold:
            sym = p.get("symbol")
            tid = p.get("trade_id")
            mode = state.get("mode") or settings.trading_state
            try:
                from tools import mt5_bridge
                from config import get_settings as gs
                s = gs()
                bridge = (s.mt5_bridge_url or "").rstrip("/") or None
                if tid:
                    res = await mt5_bridge.close_trade(str(tid), mode, bridge_url=bridge)
                    if res.get("success"):
                        closed += 1
                        actions.append({"action": "close_max_hold", "symbol": sym, "trade_id": tid})
                        continue
                    actions.append({"action": "close_failed", "symbol": sym, "error": res.get("message")})
            except Exception as e:
                logger.warning("scalp close %s failed: %s", sym, e)
                actions.append({"action": "close_failed", "symbol": sym, "error": str(e)})

        remaining.append(p)

    if closed:
        memory.store("open_positions", remaining)

    return {"actions": actions, "closed": closed}
