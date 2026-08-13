"""
MT5 Windows Bridge — run this on the Windows machine where MetaTrader5 is installed.

Usage:
    python mt5_windows_bridge.py

Environment variables (or .env file):
    MT5_LOGIN         — account number (integer)
    MT5_PASSWORD      — account password
    MT5_SERVER        — broker server name, e.g. MetaQuotes-Demo
    BRIDGE_PORT       — port to listen on (default: 5555)
    MT5_BRIDGE_SECRET — required shared secret; all write AND read endpoints
                        are rejected with 401/503 when this is not set.

Once running, set MT5_BRIDGE_URL=http://<this-machine-ip>:5555 in Replit secrets.
Run the bridge behind a firewall or VPN — never expose it on a public IP without a secret.

Install dependencies on Windows:
    pip install MetaTrader5 fastapi uvicorn python-dotenv
"""

import os
import sys
import asyncio
from datetime import datetime, timezone
from typing import Optional

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

try:
    import MetaTrader5 as mt5
except ImportError:
    print("ERROR: MetaTrader5 package not installed. Run: pip install MetaTrader5")
    sys.exit(1)

try:
    from fastapi import Depends, FastAPI, HTTPException, Header
    from pydantic import BaseModel
    import uvicorn
except ImportError:
    print("ERROR: fastapi/uvicorn not installed. Run: pip install fastapi uvicorn")
    sys.exit(1)


# ── Config ─────────────────────────────────────────────────
LOGIN    = int(os.getenv("MT5_LOGIN", "0"))
PASSWORD = os.getenv("MT5_PASSWORD", "")
SERVER   = os.getenv("MT5_SERVER", "")
PORT     = int(os.getenv("BRIDGE_PORT", "5555"))
SECRET   = os.getenv("MT5_BRIDGE_SECRET", "")  # required — all endpoints reject when missing
TERMINAL = os.getenv("MT5_TERMINAL_PATH", "").strip()

if not all([LOGIN, PASSWORD, SERVER]):
    print("ERROR: Set MT5_LOGIN, MT5_PASSWORD, MT5_SERVER in environment or .env file")
    sys.exit(1)


# ── MT5 helpers ─────────────────────────────────────────────

_MT5_READY = False

def _connect() -> bool:
    global _MT5_READY
    if _MT5_READY:
        info = mt5.account_info()
        if info is not None:
            return True
        _MT5_READY = False
    if TERMINAL:
        if not mt5.initialize(path=TERMINAL):
            print(f"MT5 initialize failed for path={TERMINAL}: {mt5.last_error()}")
            return False
    elif not mt5.initialize():
        return False
    info = mt5.account_info()
    if info is not None:
        _MT5_READY = True
        return True
    if not mt5.login(LOGIN, password=PASSWORD, server=SERVER):
        return False
    _MT5_READY = True
    return True


def _auth(x_bridge_secret: Optional[str] = Header(default=None)):
    if not SECRET:
        raise HTTPException(
            status_code=503,
            detail="Bridge write operations disabled — MT5_BRIDGE_SECRET not configured on this host",
        )
    if x_bridge_secret != SECRET:
        raise HTTPException(status_code=401, detail="Invalid bridge secret")


# ── FastAPI app ─────────────────────────────────────────────

BRIDGE_VERSION = "1.5.0-persistent-conn"
app = FastAPI(title="MT5 Windows Bridge", version=BRIDGE_VERSION)


@app.get("/version")
def version():
    return {"version": BRIDGE_VERSION}


class TradeRequest(BaseModel):
    symbol: str
    action: str       # BUY | SELL
    volume: float     # lots
    price: float      # 0 = market
    sl: float
    tp: float
    comment: str = "matrix-robot"
    magic: int = 20250518


class CloseRequest(BaseModel):
    ticket: int
    volume: Optional[float] = None  # None = full close
    comment: str = "matrix-robot-close"


class ModifyRequest(BaseModel):
    ticket: int
    sl: float = 0.0
    tp: float = 0.0


def _apply_sltp(ticket: int, symbol: str, sl: float, tp: float) -> dict:
    """Send TRADE_ACTION_SLTP to attach SL/TP (required on market-execution brokers)."""
    if sl <= 0 and tp <= 0:
        return {"success": False, "comment": "Nothing to modify (sl=0 and tp=0)"}
    request = {
        "action":   mt5.TRADE_ACTION_SLTP,
        "position": int(ticket),
        "symbol":   symbol,
        "sl":       float(sl),
        "tp":       float(tp),
        "magic":    20250518,
    }
    result = mt5.order_send(request)
    if result is None:
        return {"success": False, "comment": "order_send returned None"}
    return {
        "success": result.retcode == mt5.TRADE_RETCODE_DONE,
        "retcode": result.retcode,
        "comment": result.comment,
    }


def _resolve_position_ticket(
    symbol: str,
    magic: int,
    volume: float,
    comment: str,
    deal_ticket: int,
) -> int | None:
    from tools.bridge_ticket import resolve_position_ticket
    return resolve_position_ticket(
        mt5.positions_get, symbol, magic, volume, comment, deal_ticket,
    )


def _close_position_ticket(ticket: int) -> dict:
    pos = mt5.positions_get(ticket=int(ticket))
    if not pos:
        return {"success": True, "already_closed": True}
    p = pos[0]
    close_type = mt5.ORDER_TYPE_SELL if p.type == mt5.ORDER_TYPE_BUY else mt5.ORDER_TYPE_BUY
    tick = mt5.symbol_info_tick(p.symbol)
    price = tick.bid if p.type == mt5.ORDER_TYPE_BUY else tick.ask
    for fmode in (mt5.ORDER_FILLING_FOK, mt5.ORDER_FILLING_IOC, mt5.ORDER_FILLING_RETURN):
        result = mt5.order_send({
            "action": mt5.TRADE_ACTION_DEAL,
            "position": int(ticket),
            "symbol": p.symbol,
            "volume": p.volume,
            "type": close_type,
            "price": price,
            "magic": p.magic,
            "comment": "matrix-sltp-rollback",
            "type_time": mt5.ORDER_TIME_GTC,
            "type_filling": fmode,
        })
        if result and result.retcode != 10030:
            break
    if result and result.retcode == mt5.TRADE_RETCODE_DONE:
        return {"success": True}
    return {
        "success": False,
        "retcode": getattr(result, "retcode", None),
        "comment": getattr(result, "comment", "close failed"),
    }


@app.get("/health")
def health(_: None = Depends(_auth)):
    connected = _connect()
    info = mt5.account_info() if connected else None
    return {
        "status": "ok" if connected else "disconnected",
        "login": LOGIN,
        "server": SERVER,
        "balance":  round(info.balance, 2) if info else None,
        "equity":   round(info.equity, 2) if info else None,
        "margin_free": round(info.margin_free, 2) if info else None,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


@app.get("/account")
def account(_: None = Depends(_auth)):
    if not _connect():
        raise HTTPException(503, "MT5 connection failed")
    info = mt5.account_info()
    positions = mt5.positions_get()
    if not info:
        raise HTTPException(503, "Could not get account info")
    return {
        "login":      info.login,
        "server":     info.server,
        "balance":    round(info.balance, 2),
        "equity":     round(info.equity, 2),
        "profit":     round(info.profit, 2),
        "margin":     round(info.margin, 2),
        "margin_free": round(info.margin_free, 2),
        "margin_level": round(info.margin_level, 2) if info.margin_level else 0,
        "currency":   info.currency,
        "leverage":   info.leverage,
        "open_positions": len(positions) if positions else 0,
    }


@app.post("/trade/open")
def open_trade(req: TradeRequest, _: None = Depends(_auth)):
    if not _connect():
        raise HTTPException(503, "MT5 connection failed")

    order_type = mt5.ORDER_TYPE_BUY if req.action == "BUY" else mt5.ORDER_TYPE_SELL
    # Auto-enable symbol in Market Watch if not visible (required for trading)
    if not mt5.symbol_select(req.symbol, True):
        raise HTTPException(400, f"Symbol {req.symbol} not available on this account")
    tick = mt5.symbol_info_tick(req.symbol)
    if not tick or tick.ask == 0:
        raise HTTPException(400, f"Symbol {req.symbol} has no tick data (market closed?)")

    price = tick.ask if req.action == "BUY" else tick.bid

    # Detect symbol-supported filling modes (bitmask: 1=FOK, 2=IOC; 0/missing = RETURN-only broker)
    sym_info = mt5.symbol_info(req.symbol)
    sym_mask = getattr(sym_info, "filling_mode", 0) if sym_info else 0
    filling_modes = []
    if sym_mask & 1:
        filling_modes.append(mt5.ORDER_FILLING_FOK)
    if sym_mask & 2:
        filling_modes.append(mt5.ORDER_FILLING_IOC)
    # Always also try RETURN (works on many demo/market-execution brokers like MetaQuotes-Demo)
    filling_modes.append(mt5.ORDER_FILLING_RETURN)
    # Fallback safety: try every mode anyway if mask was empty
    for m in [mt5.ORDER_FILLING_FOK, mt5.ORDER_FILLING_IOC]:
        if m not in filling_modes:
            filling_modes.append(m)

    result = None
    for fmode in filling_modes:
        request = {
            "action":       mt5.TRADE_ACTION_DEAL,
            "symbol":       req.symbol,
            "volume":       req.volume,
            "type":         order_type,
            "price":        price,
            "sl":           req.sl,
            "tp":           req.tp,
            "magic":        req.magic,
            "comment":      req.comment,
            "type_time":    mt5.ORDER_TIME_GTC,
            "type_filling": fmode,
        }
        result = mt5.order_send(request)
        # 10030 = Unsupported filling mode — try next; otherwise stop (success or real error)
        if result is None or result.retcode != 10030:
            break

    if result is None:
        return {"success": False, "retcode": -1, "comment": "order_send returned None"}

    if result.retcode != mt5.TRADE_RETCODE_DONE:
        return {
            "success":  False,
            "retcode":  result.retcode,
            "comment":  result.comment,
        }

    actual_ticket = _resolve_position_ticket(
        req.symbol, req.magic, req.volume, req.comment, int(result.order),
    )
    if actual_ticket is None:
        return {
            "success": False,
            "retcode": result.retcode,
            "order_id": int(result.order),
            "comment": (
                "Position may have opened but ticket could not be resolved — "
                "check MT5 manually and close if unmanaged"
            ),
            "manual_check_required": True,
        }

    sltp_result = {"success": True, "skipped": True}
    if req.sl > 0 or req.tp > 0:
        positions = mt5.positions_get(ticket=actual_ticket)
        needs_sltp = True
        if positions:
            p = positions[0]
            sl_ok = req.sl <= 0 or (p.sl > 0 and abs(p.sl - req.sl) < max(1e-4, abs(req.sl) * 1e-5))
            tp_ok = req.tp <= 0 or (p.tp > 0 and abs(p.tp - req.tp) < max(1e-4, abs(req.tp) * 1e-5))
            if sl_ok and tp_ok:
                needs_sltp = False
                sltp_result = {"success": True, "already_set": True}
        if needs_sltp:
            sltp_result = _apply_sltp(actual_ticket, req.symbol, req.sl, req.tp)
            if req.sl > 0 and not sltp_result.get("success"):
                rollback = _close_position_ticket(actual_ticket)
                return {
                    "success": False,
                    "ticket": actual_ticket,
                    "retcode": sltp_result.get("retcode"),
                    "comment": f"SL/TP attach failed — position rolled back: {sltp_result.get('comment')}",
                    "sltp_followup": sltp_result,
                    "rollback": rollback,
                }

    return {
        "success":    True,
        "ticket":     actual_ticket,
        "order_id":   int(result.order),
        "symbol":     req.symbol,
        "action":     req.action,
        "volume":     req.volume,
        "price":      price,
        "sl":         req.sl,
        "tp":         req.tp,
        "sltp_followup": sltp_result,
        "comment":    req.comment,
        "retcode":    result.retcode,
        "timestamp":  datetime.now(timezone.utc).isoformat(),
    }


@app.post("/position/modify")
def modify_position(req: ModifyRequest, _: None = Depends(_auth)):
    """Set / change SL and TP on an already-open position."""
    if not _connect():
        raise HTTPException(503, "MT5 connection failed")
    pos = mt5.positions_get(ticket=req.ticket)
    if not pos:
        raise HTTPException(404, f"Position {req.ticket} not found")
    symbol = pos[0].symbol
    res = _apply_sltp(req.ticket, symbol, req.sl, req.tp)
    return {"ticket": req.ticket, "symbol": symbol, "sl": req.sl, "tp": req.tp, **res}


@app.post("/trade/close")
def close_trade(req: CloseRequest, _: None = Depends(_auth)):
    if not _connect():
        raise HTTPException(503, "MT5 connection failed")

    from tools.bridge_close import close_position
    out = close_position(
        mt5,
        ticket=req.ticket,
        volume=req.volume,
        comment=req.comment,
        connect_ok=True,
    )
    if out.get("comment") == "MT5 connection failed":
        raise HTTPException(503, out["comment"])
    return out


@app.get("/symbol/info/{symbol}")
def get_symbol_info(symbol: str, _: None = Depends(_auth)):
    if not _connect():
        raise HTTPException(503, "MT5 connection failed")
    sym = symbol.upper()
    if not mt5.symbol_select(sym, True):
        raise HTTPException(404, f"Symbol {sym} not available on this account")
    info = mt5.symbol_info(sym)
    tick = mt5.symbol_info_tick(sym)
    if not info:
        raise HTTPException(404, f"Could not load symbol info for {sym}")
    spread = None
    if tick and tick.ask and tick.bid:
        spread = round(float(tick.ask - tick.bid), int(info.digits))
    return {
        "symbol": sym,
        "point": float(info.point),
        "digits": int(info.digits),
        "trade_tick_value": float(info.trade_tick_value),
        "trade_tick_size": float(info.trade_tick_size),
        "volume_min": float(info.volume_min),
        "volume_step": float(info.volume_step),
        "volume_max": float(info.volume_max),
        "contract_size": float(getattr(info, "trade_contract_size", 0) or 0),
        "spread": spread,
        "trade_mode": int(getattr(info, "trade_mode", 0) or 0),
    }


@app.get("/positions")
def get_positions(_: None = Depends(_auth)):
    if not _connect():
        raise HTTPException(503, "MT5 connection failed")
    positions = mt5.positions_get() or []
    return {
        "positions": [
            {
                "ticket":      p.ticket,
                "symbol":      p.symbol,
                "type":        "BUY" if p.type == 0 else "SELL",
                "volume":      p.volume,
                "open_price":  p.price_open,
                "current_price": p.price_current,
                "sl":          p.sl,
                "tp":          p.tp,
                "profit":      round(p.profit, 2),
                "swap":        round(p.swap, 2),
                "comment":     p.comment,
                "open_time":   datetime.fromtimestamp(p.time, tz=timezone.utc).isoformat(),
            }
            for p in positions
        ],
        "count": len(positions),
    }


_DEAL_REASON = {
    0: "client",
    1: "mobile",
    2: "web",
    3: "expert",
    4: "stop_loss",
    5: "take_profit",
    6: "stop_out",
    7: "rollover",
    8: "external",
    9: "vmargin",
}


@app.get("/history/position/{position_id}")
def get_position_close(position_id: int, days: int = 7, _: None = Depends(_auth)):
    from datetime import timedelta

    if not _connect():
        raise HTTPException(503, "MT5 connection failed")
    date_from = datetime.now(timezone.utc) - timedelta(days=max(1, min(days, 30)))
    deals = mt5.history_deals_get(date_from, datetime.now(timezone.utc)) or []
    pid = int(position_id)
    outs = [
        d for d in deals
        if d.entry == mt5.DEAL_ENTRY_OUT and int(getattr(d, "position_id", 0) or 0) == pid
    ]
    if not outs:
        return {"found": False, "position_id": pid}
    close_deal = sorted(outs, key=lambda x: x.time)[-1]
    ins = [
        d for d in deals
        if d.entry == mt5.DEAL_ENTRY_IN and int(getattr(d, "position_id", 0) or 0) == pid
    ]
    entry_deal = sorted(ins, key=lambda x: x.time)[0] if ins else None
    profit = round(float(close_deal.profit + close_deal.swap + close_deal.commission), 2)
    return {
        "found": True,
        "position_id": pid,
        "ticket": int(close_deal.ticket),
        "symbol": close_deal.symbol,
        "volume": float(close_deal.volume),
        "entry_price": float(entry_deal.price) if entry_deal else None,
        "exit_price": float(close_deal.price),
        "profit": profit,
        "close_reason": _DEAL_REASON.get(int(close_deal.reason), f"reason_{close_deal.reason}"),
        "closed_at": datetime.fromtimestamp(close_deal.time, tz=timezone.utc).isoformat(),
    }


@app.get("/history/closed-positions")
def get_closed_positions(days: int = 1, _: None = Depends(_auth)):
    """Closed positions grouped by position_id — for V11 trade review report."""
    from datetime import timedelta

    if not _connect():
        raise HTTPException(503, "MT5 connection failed")
    date_from = datetime.now(timezone.utc) - timedelta(days=max(1, min(days, 30)))
    deals = mt5.history_deals_get(date_from, datetime.now(timezone.utc)) or []
    by_pos: dict[int, dict] = {}
    for d in deals:
        pid = int(getattr(d, "position_id", 0) or 0)
        if pid <= 0:
            continue
        rec = by_pos.setdefault(pid, {"position_id": pid, "ins": [], "outs": []})
        if d.entry == mt5.DEAL_ENTRY_IN:
            rec["ins"].append(d)
        elif d.entry == mt5.DEAL_ENTRY_OUT:
            rec["outs"].append(d)

    closed: list[dict] = []
    for pid, rec in by_pos.items():
        if not rec["outs"]:
            continue
        close_deal = sorted(rec["outs"], key=lambda x: x.time)[-1]
        entry_deal = sorted(rec["ins"], key=lambda x: x.time)[0] if rec["ins"] else None
        profit = round(
            float(close_deal.profit + close_deal.swap + close_deal.commission), 2,
        )
        opened_at = (
            datetime.fromtimestamp(entry_deal.time, tz=timezone.utc).isoformat()
            if entry_deal else None
        )
        closed_at = datetime.fromtimestamp(close_deal.time, tz=timezone.utc).isoformat()
        closed.append({
            "position_id": pid,
            "ticket": int(close_deal.ticket),
            "symbol": close_deal.symbol,
            "side": "BUY" if close_deal.type == mt5.DEAL_TYPE_BUY else "SELL",
            "volume": float(close_deal.volume),
            "entry_price": float(entry_deal.price) if entry_deal else None,
            "exit_price": float(close_deal.price),
            "pnl": profit,
            "close_reason": _DEAL_REASON.get(int(close_deal.reason), f"reason_{close_deal.reason}"),
            "opened_at": opened_at,
            "closed_at": closed_at,
        })
    closed.sort(key=lambda x: x.get("closed_at") or "")
    return {
        "count": len(closed),
        "total_pnl": round(sum(c["pnl"] for c in closed), 2),
        "positions": closed,
    }


@app.get("/history")
def get_history(days: int = 7, _: None = Depends(_auth)):
    from datetime import timedelta
    if not _connect():
        raise HTTPException(503, "MT5 connection failed")
    date_from = datetime.now(timezone.utc) - timedelta(days=days)
    deals = mt5.history_deals_get(date_from, datetime.now(timezone.utc)) or []
    closed = [d for d in deals if d.entry == mt5.DEAL_ENTRY_OUT]
    return {
        "deals": [
            {
                "ticket":  d.ticket,
                "symbol":  d.symbol,
                "type":    "BUY" if d.type == mt5.DEAL_TYPE_BUY else "SELL",
                "volume":  d.volume,
                "price":   d.price,
                "profit":  round(d.profit, 2),
                "time":    datetime.fromtimestamp(d.time, tz=timezone.utc).isoformat(),
            }
            for d in closed
        ],
        "total_profit": round(sum(d.profit for d in closed), 2),
        "count": len(closed),
    }


if __name__ == "__main__":
    print(f"Starting MT5 Bridge on port {PORT}")
    print(f"Account: {LOGIN} @ {SERVER}")
    print(f"Set in Replit: MT5_BRIDGE_URL=http://<your-ip>:{PORT}")
    uvicorn.run(app, host="0.0.0.0", port=PORT)
