"""Strategy scoring route — GET /agents/strategy/scores"""
from fastapi import APIRouter
from tools.strategy_scoring import get_scores

router = APIRouter()


@router.get("/strategy/scores")
async def strategy_scores(window: int = 50):
    return get_scores(window=window)
