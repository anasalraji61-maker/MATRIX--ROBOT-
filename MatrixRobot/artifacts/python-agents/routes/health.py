import time
from fastapi import APIRouter
from config import get_settings
from models.schemas import HealthResponse
from tools.memory import is_redis_connected, is_postgres_connected
from tools.universe_manager import universe_status

router = APIRouter()
_start_time = time.time()


@router.get("/health", response_model=HealthResponse)
async def health():
    settings = get_settings()

    from tools import llm_circuit
    llm_provider = "none"
    if settings.effective_openrouter_key and llm_circuit.is_openrouter_available():
        llm_provider = f"openrouter-{settings.primary_model.split('/')[-1]}"
    elif settings.effective_gemini_key:
        llm_provider = f"gemini-{settings.gemini_model}"
    elif settings.effective_openai_key:
        llm_provider = "openai"

    uni = universe_status(settings)
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
            "council": getattr(settings, "council_enabled", False),
            "scalping": getattr(settings, "scalping_enabled", False),
        },
        uptime_seconds=round(time.time() - _start_time, 1),
        trading_mode_profile=uni.get("trading_mode_profile", ""),
        configured_symbols_count=uni.get("configured_symbols_count", 0),
        active_symbols_count=uni.get("active_symbols_count", 0),
        disabled_symbols=uni.get("disabled_symbols", []),
        asset_class_counts=uni.get("asset_class_counts", {}),
    )
