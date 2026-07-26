"""
MetaTrader 5 bridge.

Priority order (ACTIVE mode):
  1. MT5_BRIDGE_URL set → HTTP bridge (Linux/remote → Windows MT5 server)
  2. MetaTrader5 Python lib → native (Windows only, opt-in when bridge configured)
  3. Fail-closed if bridge configured but unreachable (no silent native fallback)

Non-ACTIVE modes (PAPER_MODE / FROZEN): paper simulation only — no live orders.

Run `mt5_windows_bridge.py` on the Windows machine to expose the HTTP API.
"""
import os
import random
import uuid
import asyncio
import httpx
from datetime import datetime, timezone
from config import get_settings
from models.schemas import ExecutionResult
from tools import bridge_circuit

_MAX_BRIDGE_RETRIES = 2


async def _http_with_retry(method: str, url: str, **kwargs) -> httpx.Response:
    """HTTP call with retries + circuit breaker."""
    bridge_base = url.split("/trade")[0].split("/account")[0].split("/positions")[0]
    if bridge_circuit.is_open(bridge_base):
        raise httpx.HTTPError(f"Bridge circuit open: {bridge_base}")

    last_exc: Exception | None = None
    for attempt in range(_MAX_BRIDGE_RETRIES + 1):
        try:
            async with httpx.AsyncClient(timeout=10, headers=_bridge_headers()) as client:
                if method == "GET":
                    r = await client.get(url, **kwargs)
                else:
                    r = await client.post(url, **kwargs)
                r.raise_for_status()
                bridge_circuit.record_success(bridge_base)
                return r
        except Exception as e:
            last_exc = e
            tripped = bridge_circuit.record_failure(bridge_base, str(e))
            if tripped and bridge_circuit.should_alert(bridge_base):
                try:
                    from tools import telegram_alerts
                    if get_settings().has_telegram:
                        asyncio.create_task(
                            telegram_alerts.alert_bridge_open(bridge_base, str(e)[:200])
                        )
                except Exception:
                    pass
            if attempt < _MAX_BRIDGE_RETRIES:
                await asyncio.sleep(1.5 * (attempt + 1))
    raise last_exc or httpx.HTTPError("bridge request failed")


def _bridge_headers() -> dict:
    """Auth headers for the MT5 bridge. Sends X-Bridge-Secret when
    MT5_BRIDGE_SECRET is configured (required for public VPS deployment)."""
    secret = os.getenv("MT5_BRIDGE_SECRET", "")
    if not secret:
        # On VPS the secret lives in .env (settings), not os.environ
        secret = getattr(get_settings(), "mt5_bridge_secret", "") or ""
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
    r = await _http_with_retry(
        "POST",
        f"{bridge_url}/trade/open",
        json={"symbol": symbol, "action": action, "volume": lots,
              "price": 0, "sl": sl, "tp": tp},
    )
    return r.json()


async def _http_close(bridge_url: str, ticket: int) -> dict:
    r = await _http_with_retry(
        "POST", f"{bridge_url}/trade/close", json={"ticket": ticket},
    )
    return r.json()


async def _http_account(bridge_url: str) -> dict:
    r = await _http_with_retry("GET", f"{bridge_url}/account")
    return r.json()


async def _http_positions(bridge_url: str) -> list:
    r = await _http_with_retry("GET", f"{bridge_url}/positions")
    return r.json().get("positions", [])


async def _http_modify(bridge_url: str, ticket: int, sl: float, tp: float) -> dict:
    r = await _http_with_retry(
        "POST",
        f"{bridge_url}/position/modify",
        json={"ticket": ticket, "sl": sl, "tp": tp},
    )
    return r.json()


async def _http_symbol_info(bridge_url: str, symbol: str) -> dict:
    r = await _http_with_retry("GET", f"{bridge_url.rstrip('/')}/symbol/info/{symbol}")
    return r.json()


async def verify_position_sltp(
    bridge_url: str,
    ticket: int,
    expected_sl: float,
    expected_tp: float = 0.0,
    *,
    tol: float = 1e-4,
) -> dict:
    """Confirm SL/TP attached on live position. Returns {verified, sl, tp, ...}."""
    try:
        positions = await _http_positions(bridge_url)
    except Exception as e:
        return {"verified": False, "reason": str(e)}
    for p in positions:
        tid = p.get("ticket") or p.get("trade_id")
        if str(tid) != str(ticket):
            continue
        sl = float(p.get("sl") or p.get("stop_loss") or 0)
        tp = float(p.get("tp") or p.get("take_profit") or 0)
        sl_ok = expected_sl > 0 and sl > 0 and abs(sl - expected_sl) <= max(tol, abs(expected_sl) * 1e-5)
        tp_ok = expected_tp <= 0 or (tp > 0 and abs(tp - expected_tp) <= max(tol, abs(expected_tp) * 1e-5))
        return {
            "verified": sl_ok and tp_ok,
            "sl": sl,
            "tp": tp,
            "sl_ok": sl_ok,
            "tp_ok": tp_ok,
            "ticket": ticket,
        }
    return {"verified": False, "reason": f"Position {ticket} not found on bridge"}


def _verify_native_sltp(ticket: int, expected_sl: float, expected_tp: float = 0.0, *, tol: float = 1e-4) -> dict:
    """Confirm SL/TP on a native MT5 position."""
    if not _mt5_available or not mt5:
        return {"verified": False, "reason": "native MT5 unavailable"}
    positions = mt5.positions_get(ticket=int(ticket))
    if not positions:
        return {"verified": False, "reason": f"Position {ticket} not found"}
    pos = positions[0]
    sl = float(pos.sl or 0)
    tp = float(pos.tp or 0)
    sl_ok = expected_sl > 0 and sl > 0 and abs(sl - expected_sl) <= max(tol, abs(expected_sl) * 1e-5)
    tp_ok = expected_tp <= 0 or (tp > 0 and abs(tp - expected_tp) <= max(tol, abs(expected_tp) * 1e-5))
    return {"verified": sl_ok and tp_ok, "sl": sl, "tp": tp, "sl_ok": sl_ok, "tp_ok": tp_ok, "ticket": ticket}


def _native_modify_sltp(ticket: int, sl: float, tp: float) -> bool:
    if not _mt5_available or not mt5:
        return False
    positions = mt5.positions_get(ticket=int(ticket))
    if not positions:
        return False
    pos = positions[0]
    result = mt5.order_send({
        "action": mt5.TRADE_ACTION_SLTP,
        "position": int(ticket),
        "symbol": pos.symbol,
        "sl": sl,
        "tp": tp,
    })
    return result is not None and result.retcode == mt5.TRADE_RETCODE_DONE


def _native_close(ticket: int) -> bool:
    if not _mt5_available or not mt5:
        return False
    positions = mt5.positions_get(ticket=int(ticket))
    if not positions:
        return False
    pos = positions[0]
    close_type = mt5.ORDER_TYPE_SELL if pos.type == 0 else mt5.ORDER_TYPE_BUY
    tick = mt5.symbol_info_tick(pos.symbol)
    price = tick.bid if pos.type == 0 else tick.ask
    result = mt5.order_send({
        "action": mt5.TRADE_ACTION_DEAL,
        "symbol": pos.symbol,
        "volume": pos.volume,
        "type": close_type,
        "position": int(ticket),
        "price": price,
        "magic": 20250518,
        "comment": "matrix-sltp-rollback",
        "type_time": mt5.ORDER_TIME_GTC,
        "type_filling": mt5.ORDER_FILLING_IOC,
    })
    return result is not None and result.retcode == mt5.TRADE_RETCODE_DONE


def _bridge_fallback_blocked(settings, bridge_url: str, exc: Exception | None = None) -> ExecutionResult | None:
    """When bridge URL is set, native fallback is opt-in only."""
    if not bridge_url:
        return None
    if not getattr(settings, "active_allow_native_mt5", False):
        detail = f" ({exc})" if exc else ""
        return ExecutionResult(
            executed=False,
            mode="ACTIVE",
            message=f"Bridge configured but unreachable; native fallback disabled{detail}",
        )
    return None


async def fetch_position_close(position_id: int, bridge_url: str, days: int = 7) -> dict:
    """Return closing deal details for a position ticket (SL/TP/exit/pnl)."""
    url = (bridge_url or "").rstrip("/")
    if not url:
        return {"found": False, "position_id": position_id}
    r = await _http_with_retry(
        "GET",
        f"{url}/history/position/{int(position_id)}",
        params={"days": int(days)},
    )
    return r.json()


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
                ticket = data.get("ticket")
                sltp_ok = True
                sltp_note = ""
                if getattr(settings, "active_verify_sltp_after_open", True) and stop_loss_price > 0:
                    check = await verify_position_sltp(
                        bridge_url, int(ticket), stop_loss_price, take_profit_price,
                    )
                    if not check.get("verified"):
                        await _http_modify(
                            bridge_url, int(ticket), stop_loss_price, take_profit_price,
                        )
                        check = await verify_position_sltp(
                            bridge_url, int(ticket), stop_loss_price, take_profit_price,
                        )
                    if not check.get("verified") or float(check.get("sl") or 0) <= 0:
                        sltp_ok = False
                        sltp_note = check.get("reason", "SL not verified on position")
                        try:
                            await _http_close(bridge_url, int(ticket))
                        except Exception:
                            pass
                        return ExecutionResult(
                            executed=False, mode=mode,
                            message=f"SL/TP verification failed — order rolled back: {sltp_note}",
                        )
                    sltp_note = "SL/TP verified"
                return ExecutionResult(
                    executed=True,
                    mode=mode,
                    trade_id=str(ticket),
                    symbol=symbol,
                    action=action,
                    lots=lots,
                    entry_price=data.get("price", 0),
                    stop_loss=stop_loss_price,
                    take_profit=take_profit_price,
                    message=f"Order filled via bridge: #{ticket}" + (f" ({sltp_note})" if sltp_note else ""),
                    timestamp=datetime.now(timezone.utc).isoformat(),
                )
            else:
                if data.get("manual_check_required"):
                    from tools.bridge_manual import record_manual_check_required
                    await record_manual_check_required(symbol, data)
                    return ExecutionResult(
                        executed=False, mode=mode, symbol=symbol, action=action,
                        manual_check_required=True,
                        message=(
                            "CRITICAL: MT5 order may have opened but ticket unresolved — "
                            "check MT5 manually; new trades blocked"
                        ),
                    )
                return ExecutionResult(
                    executed=False, mode=mode,
                    message=f"Bridge error: {data.get('comment','unknown')} (retcode {data.get('retcode')})",
                )
        except Exception as exc:
            blocked = _bridge_fallback_blocked(settings, bridge_url, exc)
            if blocked:
                return blocked

    # 2 — Native MT5 (Windows)
    if bridge_url and not getattr(settings, "active_allow_native_mt5", False):
        return ExecutionResult(
            executed=False, mode=mode,
            message="Bridge configured — native MT5 path disabled (set active_allow_native_mt5=true to override)",
        )
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
            ticket = int(result.order)
            sltp_note = ""
            if getattr(settings, "active_verify_sltp_after_open", True) and stop_loss_price > 0:
                check = _verify_native_sltp(ticket, stop_loss_price, take_profit_price)
                if not check.get("verified"):
                    _native_modify_sltp(ticket, stop_loss_price, take_profit_price)
                    check = _verify_native_sltp(ticket, stop_loss_price, take_profit_price)
                if not check.get("verified") or float(check.get("sl") or 0) <= 0:
                    _native_close(ticket)
                    return ExecutionResult(
                        executed=False, mode=mode,
                        message=f"Native SL/TP verification failed — order rolled back: {check.get('reason', 'SL missing')}",
                    )
                sltp_note = "SL/TP verified"
            return ExecutionResult(
                executed=True, mode=mode,
                trade_id=str(ticket), symbol=symbol, action=action,
                lots=lots, entry_price=price,
                stop_loss=stop_loss_price, take_profit=take_profit_price,
                message=f"Order filled: #{ticket}" + (f" ({sltp_note})" if sltp_note else ""),
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
        except Exception as exc:
            if bridge_url and not getattr(settings, "active_allow_native_mt5", False):
                return {"success": False, "message": f"Bridge configured but unreachable; native fallback disabled ({exc})"}

    if bridge_url and not getattr(settings, "active_allow_native_mt5", False):
        return {"success": False, "message": "Bridge configured — native close disabled"}

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


def _native_read_allowed(settings, bridge_url: str) -> bool:
    """In ACTIVE with bridge configured, block native MT5 reads unless opt-in."""
    if not bridge_url:
        return True
    if getattr(settings, "active_allow_native_mt5", False):
        return True
    if str(getattr(settings, "trading_state", "")).upper() == "ACTIVE":
        return False
    return True


async def get_live_account(bridge_url: str | None = None) -> dict | None:
    """Fetch real account info from bridge or native MT5."""
    settings = get_settings()
    bridge_url = (bridge_url or settings.mt5_bridge_url or "").rstrip("/")
    if bridge_url:
        try:
            return await _http_account(bridge_url)
        except Exception:
            if not _native_read_allowed(settings, bridge_url):
                return None
    elif not _native_read_allowed(settings, bridge_url):
        return None
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
            if not _native_read_allowed(settings, bridge_url):
                return []
    elif not _native_read_allowed(settings, bridge_url):
        return []
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


async def modify_position(
    ticket: int,
    sl: float,
    tp: float,
    mode: str = "ACTIVE",
    bridge_url: str | None = None,
) -> dict:
    """Modify SL/TP on an open position via bridge or native MT5."""
    settings = get_settings()
    if mode != "ACTIVE":
        return {"success": True, "mode": mode, "message": "Paper modify simulated"}

    bridge_url = (bridge_url or settings.mt5_bridge_url or "").rstrip("/")
    if bridge_url:
        try:
            data = await _http_modify(bridge_url, int(ticket), sl, tp)
            return {"success": True, **data}
        except Exception as e:
            return {"success": False, "message": str(e)}

    if _mt5_available and settings.has_mt5 and _init_mt5():
        try:
            positions = mt5.positions_get(ticket=int(ticket))
            if not positions:
                return {"success": False, "message": f"Position {ticket} not found"}
            pos = positions[0]
            result = mt5.order_send({
                "action": mt5.TRADE_ACTION_SLTP,
                "position": pos.ticket,
                "symbol": pos.symbol,
                "sl": sl,
                "tp": tp if tp > 0 else pos.tp,
            })
            if result and result.retcode == mt5.TRADE_RETCODE_DONE:
                return {"success": True, "ticket": ticket, "sl": sl, "tp": tp}
            return {"success": False, "message": getattr(result, "comment", "modify failed")}
        except Exception as e:
            return {"success": False, "message": str(e)}
        finally:
            if mt5:
                mt5.shutdown()

    return {"success": False, "message": "No MT5 connection available"}
