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
            "bridge_url_configured": bool(a.bridge_url),
            "risk_per_trade_pct": a.risk_per_trade_pct,
            "max_daily_drawdown_pct": a.max_daily_drawdown_pct,
            "max_total_drawdown_pct": a.max_total_drawdown_pct,
            "account": snap,
            "open_positions": len(positions),
            "trades_today": account_state.trades_today_count(a.id if a.id != "primary" else None),
            "trades_today_max": __import__("config").get_settings().max_trades_per_day,
        })
    return {"accounts": out, "count": len(out)}


@router.get("/accounts/{account_id}/positions")
async def account_positions(account_id: str):
    """Live positions for a specific account (from its bridge if reachable,
    else from memory)."""
    a = accounts_mod.get_account(account_id)
    if not a:
        return {"error": f"unknown account {account_id}", "positions": []}
    live = []
    if a.bridge_url:
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
