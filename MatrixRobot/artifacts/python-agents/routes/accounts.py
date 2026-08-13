"""Multi-account status endpoints."""
from fastapi import APIRouter

from tools import accounts as accounts_mod, account_state, memory, mt5_bridge

router = APIRouter()


@router.get("/accounts")
async def list_accounts():
    """List all configured accounts with live equity + per-account counters.

    Each entry includes the account's own bridge status, live equity, daily
    DD, open positions in memory, and trades-today counter — so the
    dashboard can show one row per account.
    """
    out = []
    for a in accounts_mod.load_accounts():
        if not a.enabled:
            pos_key = "open_positions" if a.id == "primary" else f"open_positions__{a.id}"
            positions = memory.retrieve(pos_key) or []
            out.append({
                "id": a.id,
                "label": a.label,
                "enabled": False,
                "prop_firm": a.prop_firm,
                "account_profile": a.account_profile,
                "symbols": a.symbol_list or "all",
                "bridge_url_configured": bool(a.bridge_url),
                "risk_per_trade_pct": a.risk_per_trade_pct,
                "max_daily_drawdown_pct": a.max_daily_drawdown_pct,
                "max_total_drawdown_pct": a.max_total_drawdown_pct,
                "max_concurrent_positions": a.max_concurrent_positions or __import__("config").get_settings().max_concurrent_positions,
                "max_trades_per_day": a.max_trades_per_day or __import__("config").get_settings().max_trades_per_day,
                "min_conviction_threshold": a.min_conviction_threshold or __import__("config").get_settings().min_conviction_threshold,
                "account": {"available": False, "note": "account disabled"},
                "open_positions": len(positions),
                "trades_today": account_state.trades_today_count(a.id if a.id != "primary" else None),
                "trades_today_max": a.max_trades_per_day or __import__("config").get_settings().max_trades_per_day,
            })
            continue
        snap = await account_state.refresh_account(
            account_id=a.id,
            bridge_url=a.bridge_url or None,
            starting_balance_override=a.starting_balance or None,
        )
        pos_key = "open_positions" if a.id == "primary" else f"open_positions__{a.id}"
        positions = memory.retrieve(pos_key) or []
        out.append({
            "id": a.id,
            "label": a.label,
            "enabled": a.enabled,
            "prop_firm": a.prop_firm,
            "account_profile": a.account_profile,
            "symbols": a.symbol_list or "all",
            "bridge_url_configured": bool(a.bridge_url),
            "risk_per_trade_pct": a.risk_per_trade_pct,
            "max_daily_drawdown_pct": a.max_daily_drawdown_pct,
            "max_total_drawdown_pct": a.max_total_drawdown_pct,
            "max_concurrent_positions": a.max_concurrent_positions or __import__("config").get_settings().max_concurrent_positions,
            "max_trades_per_day": a.max_trades_per_day or __import__("config").get_settings().max_trades_per_day,
            "min_conviction_threshold": a.min_conviction_threshold or __import__("config").get_settings().min_conviction_threshold,
            "account": snap,
            "open_positions": len(positions),
            "trades_today": account_state.trades_today_count(a.id if a.id != "primary" else None),
            "trades_today_max": a.max_trades_per_day or __import__("config").get_settings().max_trades_per_day,
        })
    return {"accounts": out, "count": len(out)}


@router.get("/accounts/{account_id}/positions")
async def account_positions(account_id: str):
    """Live positions for a specific account (from its bridge if reachable,
    else from memory)."""
    a = accounts_mod.get_account(account_id)
    if not a:
        return {"error": f"unknown account {account_id}", "positions": []}
    if a.bridge_url and not a.enabled:
        return {"error": f"account {account_id} is disabled", "positions": []}
    live = []
    if a.bridge_url and a.enabled:
        try:
            live = await mt5_bridge.get_live_positions(bridge_url=a.bridge_url)
        except Exception:
            live = []
    pos_key = "open_positions" if a.id == "primary" else f"open_positions__{a.id}"
    mem_pos = memory.retrieve(pos_key) or []
    return {
        "account": a.id,
        "label": a.label,
        "live_positions": live,
        "memory_positions": mem_pos,
        "source": "mt5_live" if live else "memory",
    }
