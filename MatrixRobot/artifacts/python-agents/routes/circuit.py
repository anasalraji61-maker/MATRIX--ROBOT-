"""Circuit breaker status — GET /agents/circuit/status"""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from tools import circuit_status
from tools.bridge_manual import MANUAL_CHECK_CLEAR_PHRASE, clear, get_status, is_blocking

router = APIRouter()


class ClearManualCheckRequest(BaseModel):
    confirm: str = Field(
        ...,
        description="Must exactly match the manual-check clearance phrase",
    )


@router.get("/circuit/status")
async def get_circuit_status():
    return await circuit_status.full_report()


@router.post("/circuit/preflight")
async def run_preflight():
    from routes.trading import get_effective_mode
    return await circuit_status.preflight_cycle(get_effective_mode())


@router.post("/circuit/clear-manual-check")
async def clear_manual_check(body: ClearManualCheckRequest):
    """Admin-only: clear manual_check_required after human MT5 verification."""
    if body.confirm.strip() != MANUAL_CHECK_CLEAR_PHRASE:
        raise HTTPException(
            status_code=400,
            detail={
                "error": "confirmation_required",
                "message": MANUAL_CHECK_CLEAR_PHRASE,
            },
        )
    if not is_blocking():
        return {"cleared": False, "message": "No manual check flag active"}
    detail = get_status()
    clear()
    return {
        "cleared": True,
        "message": "Manual check cleared — trading may resume after preflight passes",
        "previous": detail,
    }
