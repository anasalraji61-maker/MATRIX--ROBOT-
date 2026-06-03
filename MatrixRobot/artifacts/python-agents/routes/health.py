import time
from fastapi import APIRouter
from config import get_settings
from models.schemas import HealthResponse
from tools.memory import is_redis_connected, is_postgres_connected

router = APIRouter()
_start_time = time.time()


@router.get("/health", response_model=HealthResponse)
async def health():
    settings = get_settings()

    from tools import llm_circuit
    llm_provider = "none"
    if settings.effective_openrouter_key and llm_circuit.is_openrouter_available():
        llm_provider = f"openrouter-claude-sonnet-4.5"
    elif settings.effective_gemini_key:
        llm_provider = f"gemini-{settings.gemini_model}"
    elif settings.effective_openai_key:
        llm_provider = "openai"

    return HealthResponse(
        status="ok",
        mode=settings.trading_state,
        llm_provider=llm_provider,
        services={
            "polygon": settings.has_polygon,
            "mt5": settings.has_mt5,
            "redis": is_redis_connected(),
            "postgres": is_postgres_connected(),
            "llm": settings.has_llm,
            "huggingface": bool(settings.huggingface_api_key),
        },
        uptime_seconds=round(time.time() - _start_time, 1),
    )
