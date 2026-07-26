"""Pure MT5 position close logic — testable without loading mt5_windows_bridge."""
from __future__ import annotations

from typing import Any


def close_position(
    mt5: Any,
    *,
    ticket: int,
    volume: float | None = None,
    comment: str = "",
    connect_ok: bool = True,
) -> dict:
    """Close an open MT5 position by ticket."""
    if not connect_ok:
        return {"success": False, "retcode": -1, "comment": "MT5 connection failed", "ticket": ticket}

    pos = mt5.positions_get(ticket=ticket)
    if not pos:
        return {"success": True, "already_closed": True, "ticket": ticket}

    p = pos[0]
    tick = mt5.symbol_info_tick(p.symbol)
    if not tick or not tick.bid or not tick.ask:
        return {
            "success": False,
            "retcode": -1,
            "comment": "tick unavailable or zero bid/ask",
            "ticket": ticket,
        }

    close_type = mt5.ORDER_TYPE_SELL if p.type == mt5.ORDER_TYPE_BUY else mt5.ORDER_TYPE_BUY
    price = tick.bid if p.type == mt5.ORDER_TYPE_BUY else tick.ask
    close_volume = volume or p.volume

    filling_modes = [
        mt5.ORDER_FILLING_FOK,
        mt5.ORDER_FILLING_IOC,
        mt5.ORDER_FILLING_RETURN,
    ]
    result = None
    for fmode in filling_modes:
        request = {
            "action": mt5.TRADE_ACTION_DEAL,
            "position": ticket,
            "symbol": p.symbol,
            "volume": close_volume,
            "type": close_type,
            "price": price,
            "magic": p.magic,
            "comment": comment,
            "type_time": mt5.ORDER_TIME_GTC,
            "type_filling": fmode,
        }
        result = mt5.order_send(request)
        if result is None or result.retcode != 10030:
            break

    if result is None:
        return {
            "success": False,
            "retcode": -1,
            "comment": "close order_send returned None",
            "ticket": ticket,
        }

    if result.retcode == mt5.TRADE_RETCODE_DONE:
        return {"success": True, "ticket": ticket, "retcode": result.retcode}
    return {"success": False, "retcode": result.retcode, "comment": result.comment, "ticket": ticket}
