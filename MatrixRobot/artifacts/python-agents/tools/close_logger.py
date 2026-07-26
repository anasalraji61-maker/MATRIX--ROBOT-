"""Phase 1.3 — persist closed trades to Postgres with MT5 deal details."""
from __future__ import annotations

import logging
from datetime import datetime, timezone

from config import get_settings
from tools import memory, mt5_bridge
from tools import account_state

logger = logging.getLogger("matrix.close_logger")

# MT5 DEAL_REASON_* (MetaTrader5 Python constants)
_REASON_LABELS = {
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


def normalize_close_reason(raw: str | None) -> str:
    if not raw:
        return "unknown"
    key = str(raw).strip().lower()
    if key in _REASON_LABELS.values():
        return key
    if key.startswith("reason_"):
        try:
            code = int(key.split("_", 1)[1])
            return _REASON_LABELS.get(code, key)
        except (ValueError, IndexError):
            pass
    return key


async def log_position_closed(
    position: dict,
    *,
    account_id: str | None = None,
    bridge_url: str | None = None,
    source: str = "reconcile",
) -> dict:
    """Fetch MT5 close deal when possible, write trade_outcomes, alert Telegram."""
    from tools import prop_rules

    trade_id = str(position.get("trade_id") or position.get("ticket") or "")
    symbol = str(position.get("symbol") or "").upper()
    side = str(position.get("action") or position.get("side") or "").upper()
    acct = account_id or position.get("account") or "primary"

    deal: dict = {}
    if bridge_url and trade_id.isdigit():
        try:
            deal = await mt5_bridge.fetch_position_close(int(trade_id), bridge_url)
        except Exception as e:
            logger.warning("Close deal fetch failed for %s: %s", trade_id, e)

    entry = deal.get("entry_price") or position.get("entry_price") or position.get("entry")
    exit_px = deal.get("exit_price")
    pnl = deal.get("profit")
    if pnl is None:
        pnl = position.get("pnl")
    volume = deal.get("volume") or position.get("lots") or position.get("volume")
    reason = normalize_close_reason(deal.get("close_reason") or position.get("close_reason") or f"{source}_close")
    closed_at = deal.get("closed_at") or datetime.now(timezone.utc).isoformat()
    opened_at = position.get("opened_at") or deal.get("open_time")
    hold_minutes = None
    if opened_at and closed_at:
        try:
            o_dt = datetime.fromisoformat(str(opened_at).replace("Z", "+00:00"))
            c_dt = datetime.fromisoformat(str(closed_at).replace("Z", "+00:00"))
            hold_minutes = round(max(0, (c_dt - o_dt).total_seconds() / 60), 1)
        except Exception:
            pass

    outcome = {
        "ts": closed_at,
        "closed_at": closed_at,
        "opened_at": opened_at,
        "hold_minutes": hold_minutes,
        "ticket": int(trade_id) if trade_id.isdigit() else trade_id,
        "trade_id": trade_id,
        "symbol": symbol or "UNKNOWN",
        "side": side or None,
        "entry": entry,
        "entry_price": entry,
        "exit": exit_px,
        "exit_price": exit_px,
        "volume": volume,
        "pnl": float(pnl) if pnl is not None else None,
        "reason": reason,
        "close_reason": reason,
        "account": acct,
        "mode": "ACTIVE",
        "source": source,
        "deal_found": bool(deal.get("found")),
        "trade_style": position.get("trade_tier") or position.get("trade_style"),
        "strategy_name": position.get("strategy_name") or position.get("strategy"),
    }
    for key in (
        "trade_tier", "strategy", "strategy_name", "strength",
        "stop_loss", "take_profit", "initial_stop_loss",
        "spread_at_entry", "spread_pips", "council_approved", "council_meta_score",
        "entry_reason", "scalp_strategy", "skeptic_vote", "risk_vote",
    ):
        if position.get(key) is not None:
            outcome[key] = position.get(key)

    memory.log_trade_outcome(outcome)

    if pnl is not None and side in ("BUY", "SELL") and symbol:
        try:
            from tools import rl_filter
            rl_filter.record_trade_close(symbol, side, float(pnl))
        except Exception as e:
            logger.debug("RL outcome record skipped: %s", e)

    if pnl is not None:
        try:
            prop_rules.record_daily_pnl(float(pnl))
        except Exception:
            pass
        try:
            account_state.record_qualified_trade_close(acct if acct != "primary" else None)
        except Exception:
            pass

    try:
        from tools import telegram_alerts
        if get_settings().has_telegram:
            await telegram_alerts.alert_trade_closed(
                account=str(acct),
                symbol=symbol,
                side=side,
                pnl=float(pnl) if pnl is not None else None,
                reason=reason,
                ticket=trade_id,
            )
    except Exception:
        logger.exception("Telegram close alert failed for %s", trade_id)

    closed = {
        "trade_id": trade_id,
        "symbol": symbol,
        "side": side,
        "account": acct,
        "close_reason": reason,
        "pnl": float(pnl) if pnl is not None else None,
        "closed_at": closed_at,
        "entry": entry,
        "exit": exit_px,
    }
    logger.info(
        "Logged close %s %s %s pnl=%s reason=%s",
        trade_id, symbol, side, pnl, reason,
    )
    return closed
