"""ML signal filter status — GET /agents/ml/status"""
from fastapi import APIRouter
from tools import ml_filter, ml_retrain_scheduler, rl_filter

router = APIRouter()


@router.get("/ml/status")
async def ml_status():
    from tools import mistake_learner, self_learning, loss_investigator, evolution_entity

    return {
        "filter": ml_filter.get_status(),
        "retrain": ml_retrain_scheduler.get_status(),
        "rl": rl_filter.get_status(),
        "mistake_learner": mistake_learner.get_snapshot(),
        "self_learning": self_learning.get_snapshot(),
        "loss_investigator": loss_investigator.get_snapshot(),
        "evolution_entity": evolution_entity.get_snapshot(),
        "lab_note": (
            "Evolution Entity + self-learning run CONTINUOUSLY on VPS cloud. "
            "Laptop RTX is only for heavy PyTorch training / model export."
        ),
    }


@router.post("/ml/retrain")
async def ml_retrain_now():
    """Manual retrain trigger (needs PyTorch — prefer laptop ML Lab)."""
    return await ml_retrain_scheduler.run_retrain_once()
