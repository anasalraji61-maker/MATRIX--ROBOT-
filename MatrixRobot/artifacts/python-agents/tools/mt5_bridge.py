"""
MetaTrader 5 bridge.

Priority order:
  1. MT5_BRIDGE_URL set → HTTP bridge (Linux/remote → Windows MT5 server)
  2. MetaTrader5 Python lib available → native (Windows only)
  3. Fallback → paper simulation

Run `mt5_windows_bridge.py` on the Windows machine to expose the HTTP API.
"""
import os
import random
import uuid
import httpx
from datetime import datetime, timezone
from config import get_settings
from models.schemas import ExecutionResult


def _bridge_headers() -> dict:
    """Auth headers for the MT5 bridge. Sends X-Bridge-Secret when
    MT5_BRIDGE_SECRET is configured (required for public VPS deployment)."""
    secret = os.getenv("MT5_BRIDGE_SECRET", "")
    return {"X-Bridge-Secret": secret} if secret else {}

_mt5_available = False
try:
    import MetaTrader5 as mt5
    _mt5_available = True
except ImportError:
    mt5 = None  # type: ignore


# ──────────────────────────────────────────────────────────
# HTTP bridge (Linux → Windows bridge server)
# ──────────────────────────────────────────────────────────

async def _http_open(
    bridge_url: str,
    symbol: str,
    action: str,
    lots: float,
    sl: float,
    tp: float,
) -> dict:
    async with httpx.AsyncClient(timeout=10, headers=_bridge_headers()) as client:
        r = await client.post(
            f"{bridge_url}/trade/open",
            json={"symbol": symbol, "action": action, "volume": lots,
                  "price": 0, "sl": sl, "tp": tp},
        )
        r.raise_for_status()
        return r.json()


async def _http_close(bridge_url: str, ticket: int) -> dict:
    async with httpx.AsyncClient(timeout=10, headers=_bridge_headers()) as client:
        r = await client.post(f"{bridge_url}/trade/close", json={"ticket": ticket})
        r.raise_for_status()
        return r.json()


async def _http_account(bridge_url: str) -> dict:
    async with httpx.AsyncClient(timeout=5, headers=_bridge_headers()) as client:
        r = await client.get(f"{bridge_url}/account")
        r.raise_for_status()
        return r.json()


async def _http_positions(bridge_url: str) -> list:
    async with httpx.AsyncClient(timeout=5, headers=_bridge_headers()) as client:
        r = await client.get(f"{bridge_url}/positions")
        r.raise_for_status()
        return r.json().get("positions", [])


# ──────────────────────────────────────────────────────────
# Native MT5 (Windows only)
# ──────────────────────────────────────────────────────────

import logging as _logging
_mt5_log = _logging.getLogger("matrix.mt5")


_MT5_CANDIDATE_PATHS = [
    # Launch-first strategy: specify path so Python starts terminal fresh.
    # This avoids IPC timeout that occurs when attaching to a user-opened terminal
    # on Windows Server 2025 (confirmed working on this VPS).
    r"C:\Program Files\MetaTrader 5\terminal64.exe",
    r"C:\Program Files (x86)\MetaTrader 5\terminal64.exe",
    r"C:\MetaTrader 5\terminal64.exe",
    r"C:\MT5\terminal64.exe",
    None,  # auto-detect last resort
]


def _init_mt5() -> bool:
    """Connect to running MT5 terminal and login.

    Tries multiple strategies:
      1. initialize(login=...) with auto-detect path
      2. initialize(path=<candidate>, login=...) for each known install path
      3. plain initialize() then login() as last resort
    """
    if not _mt5_available or mt5 is None:
        return False
    settings = get_settings()
    if not settings.has_mt5:
        return False
    try:
        login_id = int(settings.mt5_login)

        # Strategy 1: use explicit path (lets Python launch the terminal).
        # Do NOT call mt5.shutdown() between attempts — that kills the terminal
        # Python just launched and causes the reopen loop.
        primary_path = r"C:\Program Files\MetaTrader 5\terminal64.exe"
        try:
            ok = mt5.initialize(path=primary_path)
        except Exception:
            ok = False
        if ok:
            _mt5_log.info(f"MT5 initialized OK (path={primary_path})")
            return True
        err = mt5.last_error()
        _mt5_log.warning(f"MT5 initialize(path={primary_path}) failed: {err}")

        # Strategy 2: plain initialize (attach to already-running terminal)
        try:
            ok2 = mt5.initialize()
        except Exception:
            ok2 = False
        if ok2:
            _mt5_log.info("MT5 initialized OK (auto-detect)")
            return True
        err2 = mt5.last_error()
        _mt5_log.warning(f"MT5 initialize() auto failed: {err2}")
        mt5.shutdown()
        return False
    except Exception as exc:
        _mt5_log.warning(f"MT5 init exception: {exc}")
        return False


async def diagnose_mt5() -> dict:
    """Return a diagnostic snapshot of MT5 connectivity — for the /debug/mt5 route."""
    import asyncio
    if not _mt5_available or mt5 is None:
        return {"library": False, "reason": "MetaTrader5 package not installed"}
    settings = get_settings()
    if not settings.has_mt5:
        return {"library": True, "credentials": False, "reason": "MT5_LOGIN/PASSWORD/SERVER not set"}

    def _sync_diagnose():
        connected = _init_mt5()
        if not connected:
            last_err = mt5.last_error() if mt5 else "n/a"
            return {"library": True, "credentials": True, "connected": False,
                    "last_error": str(last_err)}
        info = mt5.account_info()
        terminal = mt5.terminal_info()
        mt5.shutdown()
        return {
            "library": True,
            "credentials": True,
            "connected": True,
            "account": {
                "login": info.login if info else None,
                "server": info.server if info else None,
                "balance": info.balance if info else None,
                "equity": info.equity if info else None,
                "currency": info.currency if info else None,
            },
            "terminal": {
                "path": terminal.path if terminal else None,
                "connected": terminal.connected if terminal else None,
                "trade_allowed": terminal.trade_allowed if terminal else None,
            },
        }

    try:
        result = await asyncio.wait_for(
            asyncio.get_event_loop().run_in_executor(None, _sync_diagnose),
            timeout=10.0,
        )
        return result
    except asyncio.TimeoutError:
        return {"library": True, "credentials": True, "connected": False,
                "last_error": "mt5.initialize() timed out (10s) — is MT5 terminal running?"}


# ──────────────────────────────────────────────────────────
# Paper simulation
# ──────────────────────────────────────────────────────────

def _paper_fill(symbol: str, action: str, lots: float, sl: float, tp: float, mode: str) -> ExecutionResult:
    bases = {"EURUSD": 1.0850, "GBPUSD": 1.2700, "USDJPY": 149.50, "XAUUSD": 2320.0}
    price = round(bases.get(symbol, 1.0) * random.uniform(0.9999, 1.0001), 5)
    return ExecutionResult(
        executed=True,
        mode=mode,
        trade_id=str(uuid.uuid4())[:8],
        symbol=symbol,
        action=action,
        lots=lots,
        entry_price=price,
        stop_loss=sl,
        take_profit=tp,
        message=f"Paper fill at {price} — no real money at risk",
        timestamp=datetime.now(timezone.utc).isoformat(),
    )


# ──────────────────────────────────────────────────────────
# Public API
# ──────────────────────────────────────────────────────────

async def open_trade(
    symbol: str,
    action: str,
    lots: float,
    stop_loss_price: float,
    take_profit_price: float,
    mode: str,
    bridge_url: str | None = None,
) -> ExecutionResult:
    """Open a trade. `bridge_url` overrides settings.mt5_bridge_url so the
    same function can target different MT5 accounts in multi-account mode."""
    settings = get_settings()

    if mode != "ACTIVE":
        return _paper_fill(symbol, action, lots, stop_loss_price, take_profit_price, mode)

    # 1 — HTTP bridge (per-call override > settings)
    bridge_url = (bridge_url or settings.mt5_bridge_url or "").rstrip("/")
    if bridge_url:
        try:
            data = await _http_open(bridge_url, symbol, action, lots, stop_loss_price, take_profit_price)
            if data.get("success"):
                return ExecutionResult(
                    executed=True,
                    mode=mode,
                    trade_id=str(data.get("ticket", "")),
                    symbol=symbol,
                    action=action,
                    lots=lots,
                    entry_price=data.get("price", 0),
                    stop_loss=stop_loss_price,
                    take_profit=take_profit_price,
                    message=f"Order filled via bridge: #{data.get('ticket')}",
                    timestamp=datetime.now(timezone.utc).isoformat(),
                )
            else:
                return ExecutionResult(
                    executed=False, mode=mode,
                    message=f"Bridge error: {data.get('comment','unknown')} (retcode {data.get('retcode')})",
                )
        except Exception:
            pass  # Bridge unreachable — fall through to native MT5

    # 2 — Native MT5 (Windows)
    if not settings.has_mt5:
        return ExecutionResult(
            executed=False, mode=mode,
            message="No MT5 connection: set MT5_BRIDGE_URL (remote) or MT5_LOGIN/PASSWORD/SERVER (Windows)",
        )

    connected = _init_mt5()
    if not connected:
        return ExecutionResult(executed=False, mode=mode, message="MT5 login failed — check credentials")

    try:
        order_type = mt5.ORDER_TYPE_BUY if action == "BUY" else mt5.ORDER_TYPE_SELL
        tick = mt5.symbol_info_tick(symbol)
        price = tick.ask if action == "BUY" else tick.bid
        result = mt5.order_send({
            "action":       mt5.TRADE_ACTION_DEAL,
            "symbol":       symbol,
            "volume":       lots,
            "type":         order_type,
            "price":        price,
            "sl":           stop_loss_price,
            "tp":           take_profit_price,
            "magic":        20250518,
            "comment":      "matrix-robot",
            "type_time":    mt5.ORDER_TIME_GTC,
            "type_filling": mt5.ORDER_FILLING_IOC,
        })
        if result.retcode == mt5.TRADE_RETCODE_DONE:
            return ExecutionResult(
                executed=True, mode=mode,
                trade_id=str(result.order), symbol=symbol, action=action,
                lots=lots, entry_price=price,
                stop_loss=stop_loss_price, take_profit=take_profit_price,
                message=f"Order filled: #{result.order}",
                timestamp=datetime.now(timezone.utc).isoformat(),
            )
        return ExecutionResult(executed=False, mode=mode,
                               message=f"MT5 error: {result.comment} (retcode {result.retcode})")
    except Exception as e:
        return ExecutionResult(executed=False, mode=mode, message=f"MT5 exception: {e}")
    finally:
        if mt5:
            mt5.shutdown()


async def close_trade(trade_id: str, mode: str, bridge_url: str | None = None) -> dict:
    settings = get_settings()

    if mode != "ACTIVE":
        return {"success": True, "mode": mode, "message": f"Paper trade {trade_id} closed (simulated)"}

    bridge_url = (bridge_url or settings.mt5_bridge_url or "").rstrip("/")
    if bridge_url:
        try:
            data = await _http_close(bridge_url, int(trade_id))
            return data
        except Exception:
            pass  # Bridge unreachable — fall through to native MT5

    # Native MT5 close
    if _mt5_available and settings.has_mt5 and _init_mt5():
        try:
            positions = mt5.positions_get(ticket=int(trade_id))
            if not positions:
                return {"success": False, "message": f"Position {trade_id} not found"}
            pos = positions[0]
            close_type = mt5.ORDER_TYPE_SELL if pos.type == 0 else mt5.ORDER_TYPE_BUY
            tick = mt5.symbol_info_tick(pos.symbol)
            price = tick.bid if pos.type == 0 else tick.ask
            result = mt5.order_send({
                "action": mt5.TRADE_ACTION_DEAL,
                "symbol": pos.symbol,
                "volume": pos.volume,
                "type": close_type,
                "position": pos.ticket,
                "price": price,
                "magic": 20250518,
                "comment": "matrix-robot-close",
                "type_time": mt5.ORDER_TIME_GTC,
                "type_filling": mt5.ORDER_FILLING_IOC,
            })
            if result.retcode == mt5.TRADE_RETCODE_DONE:
                return {"success": True, "message": f"Position {trade_id} closed via native MT5"}
            return {"success": False, "message": f"MT5 close error: {result.comment}"}
        except Exception as e:
            return {"success": False, "message": f"MT5 close exception: {e}"}
        finally:
            if mt5:
                mt5.shutdown()

    return {"success": False, "message": "No MT5 connection available"}


async def get_live_account(bridge_url: str | None = None) -> dict | None:
    """Fetch real account info from bridge or native MT5."""
    settings = get_settings()
    bridge_url = (bridge_url or settings.mt5_bridge_url or "").rstrip("/")
    if bridge_url:
        try:
            return await _http_account(bridge_url)
        except Exception:
            pass  # Bridge unreachable — fall through to native MT5
    if _mt5_available and settings.has_mt5 and _init_mt5():
        info = mt5.account_info()
        mt5.shutdown()
        if info:
            return {
                "balance": round(info.balance, 2),
                "equity":  round(info.equity, 2),
                "profit":  round(info.profit, 2),
                "margin_free": round(info.margin_free, 2),
                "currency": info.currency,
            }
    return None


async def get_live_positions(bridge_url: str | None = None) -> list:
    """Fetch open positions from bridge or native MT5."""
    settings = get_settings()
    bridge_url = (bridge_url or settings.mt5_bridge_url or "").rstrip("/")
    if bridge_url:
        try:
            return await _http_positions(bridge_url)
        except Exception:
            pass  # Bridge unreachable — fall through to native MT5
    if _mt5_available and settings.has_mt5 and _init_mt5():
        positions = mt5.positions_get() or []
        mt5.shutdown()
        return [
            {
                "ticket": p.ticket,
                "symbol": p.symbol,
                "type": "BUY" if p.type == 0 else "SELL",
                "volume": p.volume,
                "open_price": p.price_open,
                "current_price": p.price_current,
                "sl": p.sl,
                "tp": p.tp,
                "profit": round(p.profit, 2),
                "open_time": datetime.fromtimestamp(p.time, tz=timezone.utc).isoformat(),
            }
            for p in positions
        ]
    return []
