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
    if not mt5.initialize():
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
    """Send a TRADE_ACTION_SLTP request to set/modify SL/TP on an open position.
    Required for brokers in 'Market Execution' mode (e.g. MetaQuotes-Demo),
    where SL/TP fields in the initial DEAL request are silently dropped."""
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

    if result.retcode != mt5.TRADE_RETCODE_DONE:
        return {
            "success":  False,
            "retcode":  result.retcode,
            "comment":  result.comment,
        }

    # Position opened. On Market-Execution brokers (MetaQuotes-Demo, many
    # prop-firm accounts) the sl/tp fields in TRADE_ACTION_DEAL are silently
    # dropped — we MUST send a follow-up TRADE_ACTION_SLTP to actually attach
    # the stop-loss / take-profit to the new position.
    ticket = result.order  # for market execution, this is the position id
    sltp_result = {"success": True, "skipped": True}
    if req.sl > 0 or req.tp > 0:
        # Verify SL/TP didn't get applied in the initial fill (instant-execution brokers)
        positions = mt5.positions_get(ticket=ticket)
        needs_sltp = True
        if positions:
            p = positions[0]
            if (req.sl <= 0 or abs(p.sl - req.sl) < 1e-6) and (req.tp <= 0 or abs(p.tp - req.tp) < 1e-6):
                needs_sltp = False
                sltp_result = {"success": True, "already_set": True}
        if needs_sltp:
            sltp_result = _apply_sltp(ticket, req.symbol, req.sl, req.tp)


    return {
        "success":    True,
        "ticket":     ticket,
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

    pos = mt5.positions_get(ticket=req.ticket)
    if not pos:
        raise HTTPException(404, f"Position {req.ticket} not found")

    p = pos[0]
    close_type = mt5.ORDER_TYPE_SELL if p.type == mt5.ORDER_TYPE_BUY else mt5.ORDER_TYPE_BUY
    tick = mt5.symbol_info_tick(p.symbol)
    price = tick.bid if p.type == mt5.ORDER_TYPE_BUY else tick.ask
    volume = req.volume or p.volume

    filling_modes = [mt5.ORDER_FILLING_FOK, mt5.ORDER_FILLING_IOC, mt5.ORDER_FILLING_RETURN]
    result = None
    for fmode in filling_modes:
        request = {
            "action":       mt5.TRADE_ACTION_DEAL,
            "position":     req.ticket,
            "symbol":       p.symbol,
            "volume":       volume,
            "type":         close_type,
            "price":        price,
            "magic":        p.magic,
            "comment":      req.comment,
            "type_time":    mt5.ORDER_TIME_GTC,
            "type_filling": fmode,
        }
        result = mt5.order_send(request)
        if result is None or result.retcode != 10030:
            break


    if result.retcode == mt5.TRADE_RETCODE_DONE:
        return {"success": True, "ticket": req.ticket, "retcode": result.retcode}
    else:
        return {"success": False, "retcode": result.retcode, "comment": result.comment}


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
