"""News + sentiment pipeline status (no LLM cost for status check)."""
from fastapi import APIRouter

from config import get_settings
from tools.news_feed import fetch_news, get_last_meta

router = APIRouter()


@router.get("/news/status")
async def news_status():
    settings = get_settings()
    meta = get_last_meta()

    sentiment_chain = []
    if settings.huggingface_api_key:
        sentiment_chain.append("finbert")
    if settings.effective_openrouter_key:
        sentiment_chain.append("gpt4o_mini_briefing")
        sentiment_chain.append("openrouter_gpt4o_mini_fallback")
    sentiment_chain.append("keyword_fallback")
    if settings.has_database:
        sentiment_chain.append("pgvector_similar_context")

    return {
        "polygon_configured": settings.has_polygon,
        "huggingface_configured": bool(settings.huggingface_api_key),
        "openrouter_configured": bool(settings.effective_openrouter_key),
        "active_require_live_news": getattr(settings, "active_require_live_news", True),
        "news_feed": meta,
        "sentiment_chain": sentiment_chain,
        "recommendation": (
            "Set POLYGON_API_KEY in .env for live headlines (free at polygon.io). "
            "Mock news is disabled by default (NEWS_ALLOW_MOCK=false). "
            "Economic calendar still works without headlines."
        ),
    }


@router.post("/news/refresh")
async def news_refresh():
    """Force-refresh headlines (bypasses 15-min cache)."""
    from tools import news_feed as nf
    nf._cache["expires"] = 0
    items = await fetch_news([], limit=12)
    return {
        "ok": True,
        "count": len(items),
        "source": get_last_meta().get("source"),
        "headlines": [n.title for n in items[:5]],
    }

