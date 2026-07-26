"""MT5 position reconciliation status — no LLM, local bridge only."""
from fastapi import APIRouter

from tools import position_reconciler, memory, prop_rules, account_state
from config import get_settings

router = APIRouter()


@router.get("/positions/reconcile/status")
async def reconcile_status():
    settings = get_settings()
    status = position_reconciler.get_status()
    mem_pos = memory.retrieve("open_positions") or []
    acct = await account_state.refresh_account()
    equity = float(acct.get("equity") or 0.0)
    margin_pct = prop_rules.margin_used_pct(mem_pos, equity) if equity > 0 else 0.0
    return {
        **status,
        "memory_open_count": len(mem_pos),
        "margin_used_pct_real": round(margin_pct, 2),
        "small_trades_today": account_state.small_trades_today_count(),
        "small_trade_limits": {
            "enabled": settings.enable_small_trades,
            "max_per_day": settings.small_trade_max_per_day,
            "max_open": settings.small_trade_max_open,
            "min_strength": settings.small_trade_min_strength,
            "normal_min_strength": settings.normal_trade_min_strength,
        },
    }


@router.post("/positions/reconcile/run")
async def reconcile_run():
    result = await position_reconciler.reconcile_all(force=True)
    return {"ok": True, "status": result}
