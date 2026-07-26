"""Telegram alerting — push robot events to your phone (free via Bot API)."""
from __future__ import annotations

import logging
from typing import Optional

import httpx

from config import get_settings

logger = logging.getLogger("matrix.telegram")

_API = "https://api.telegram.org/bot{token}/sendMessage"


def is_configured() -> bool:
    s = get_settings()
    return bool(s.telegram_bot_token and s.telegram_chat_id)


async def send(
    text: str,
    *,
    level: str = "info",
    parse_mode: Optional[str] = None,
    disable_notification: bool = False,
) -> bool:
    """Send a message. Returns True on success."""
    s = get_settings()
    if not s.telegram_bot_token or not s.telegram_chat_id:
        return False

    icons = {
        "info": "ℹ️",
        "ok": "✅",
        "warn": "⚠️",
        "error": "🔴",
        "trade": "📈",
        "cycle": "🔄",
    }
    prefix = icons.get(level, "")
    body = f"{prefix} {text}".strip() if prefix else text
    if len(body) > 4000:
        body = body[:3990] + "…"

    url = _API.format(token=s.telegram_bot_token)
    payload = {
        "chat_id": s.telegram_chat_id,
        "text": body,
        "disable_notification": disable_notification,
    }
    if parse_mode:
        payload["parse_mode"] = parse_mode

    try:
        async with httpx.AsyncClient(timeout=12.0) as client:
            r = await client.post(url, json=payload)
            if r.status_code != 200:
                logger.warning("Telegram HTTP %s: %s", r.status_code, r.text[:200])
                return False
            return bool(r.json().get("ok"))
    except Exception as e:
        logger.warning("Telegram send failed: %s", e)
        return False


async def alert_startup(mode: str, postgres: bool, interval: int | None) -> None:
    await send(
        "Matrix Robot Brain started\n"
        f"Mode: {mode}\n"
        f"Postgres: {'OK' if postgres else 'off (in-memory)'}\n"
        f"Scheduler: {f'every {interval} min' if interval else 'manual'}",
        level="ok",
    )


async def alert_cycle_skipped(cycle_id: str, reason: str, message: str) -> None:
    await send(
        f"Cycle {cycle_id} SKIPPED\n"
        f"Reason: {reason}\n"
        f"{message}",
        level="warn",
        disable_notification=True,
    )


async def alert_cycle_summary(
    cycle_id: str,
    mode: str,
    decision: dict | None,
    sentiment: dict | None,
    execution: dict | None,
    duration_ms: int,
    errors: list | None,
) -> None:
    dec = decision or {}
    sent = sentiment or {}
    exe = execution or {}
    action = dec.get("action", "HOLD")
    sym = dec.get("symbol", "-")
    conf = dec.get("confidence", 0)
    approved = dec.get("approved_trades") or []
    approved_txt = ", ".join(
        f"{t.get('symbol')} {t.get('signal')}" for t in approved[:5]
    ) or "none"
    briefing = (sent.get("briefing") or "")[:400]
    label = sent.get("label", "NEUTRAL")
    score = sent.get("score", 0)
    exe_msg = exe.get("message") or ("filled" if exe.get("executed") else "no fill")

    lines = [
        f"Cycle {cycle_id} ({duration_ms}ms)",
        f"Decision: {action} {sym} ({conf:.2f})" if conf else f"Decision: {action} {sym}",
        f"Approved ({len(approved)}): {approved_txt}",
        f"Sentiment: {label} ({score:+.2f})",
    ]
    if briefing:
        lines.append(f"Brief: {briefing}")
    lines.append(f"Execution: {exe_msg}")
    if errors:
        lines.append(f"Errors: {errors[0][:120]}")
    await send("\n".join(lines), level="cycle")


async def alert_trade_closed(
    account: str,
    symbol: str,
    side: str,
    pnl: float | None,
    reason: str,
    ticket: str,
) -> None:
    pnl_txt = f"{pnl:+.2f}" if pnl is not None else "n/a"
    await send(
        f"Trade closed [{account}]\n"
        f"#{ticket} {side} {symbol}\n"
        f"PnL: {pnl_txt} | {reason}",
        level="trade" if (pnl or 0) >= 0 else "warn",
    )


async def alert_trade(
    account: str,
    symbol: str,
    action: str,
    lots: float,
    entry: float,
    sl: float,
    tp: float,
) -> None:
    await send(
        f"Trade opened [{account}]\n"
        f"{action} {symbol} {lots} lot\n"
        f"Entry {entry} SL {sl} TP {tp}",
        level="trade",
    )


async def alert_emergency(message: str) -> None:
    await send(f"EMERGENCY: {message}", level="error")


async def alert_manual_check_required(symbol: str, detail: dict) -> None:
    order_id = detail.get("order_id", "?")
    await send(
        "CRITICAL: MT5 order may have opened but position ticket could not be resolved. "
        f"Check MT5 manually immediately.\n"
        f"Symbol: {symbol}\nOrder ID: {order_id}",
        level="error",
    )


async def alert_bridge_open(bridge_url: str, reason: str) -> None:
    await send(
        f"Bridge circuit OPEN — trading paused\n"
        f"URL: {bridge_url}\n"
        f"Reason: {reason}",
        level="error",
    )


async def alert_openrouter_circuit(reason: str) -> None:
    await send(f"OpenRouter circuit OPEN (30m cooldown)\n{reason}", level="warn")


async def alert_low_dd(daily_dd: float, threshold: float) -> None:
    await send(
        f"Drawdown warning: daily {daily_dd:.2f}% (soft cap {threshold}%)",
        level="warn",
    )
