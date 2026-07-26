"""ML signal filter status — GET /agents/ml/status"""
from fastapi import APIRouter
from tools import ml_filter, ml_retrain_scheduler, rl_filter

router = APIRouter()


@router.get("/ml/status")
async def ml_status():
    return {
        "filter": ml_filter.get_status(),
        "retrain": ml_retrain_scheduler.get_status(),
        "rl": rl_filter.get_status(),
    }
