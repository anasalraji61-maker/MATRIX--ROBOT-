"""Unified news feed for the Brain trading cycle.

Priority:
  1. Polygon.io real headlines (when POLYGON_API_KEY is set)
  2. Empty feed with source=none (never fake headlines in production)

Cached 15 minutes to respect Polygon free-tier limits.
"""
from __future__ import annotations

import logging
import time
from datetime import datetime, timezone
from typing import Any

from config import get_settings
from models.schemas import NewsItem

logger = logging.getLogger("matrix.news")

_NEWS_TTL = 900  # seconds
_cache: dict[str, Any] = {"items": [], "source": "none", "expires": 0.0, "error": None}


def get_last_meta() -> dict[str, Any]:
    """Last fetch metadata for /agents/news/status."""
    return {
        "source": _cache.get("source", "none"),
        "count": len(_cache.get("items") or []),
        "cached_until": _cache.get("expires"),
        "last_error": _cache.get("error"),
    }


async def fetch_news(symbols: list[str], limit: int = 12) -> list[NewsItem]:
    """Fetch headlines for the brain cycle. Returns [] when no live source."""
    now = time.time()
    if _cache.get("items") and (_cache.get("expires") or 0) > now:
        return list(_cache["items"])

    settings = get_settings()
    items: list[NewsItem] = []
    source = "none"
    err: str | None = None

    if settings.has_polygon:
        try:
            from tools.polygon import fetch_forex_news
            items = await fetch_forex_news(limit=limit)
            if items:
                source = "polygon"
            else:
                err = "polygon_empty"
        except Exception as e:
            err = str(e)
            logger.warning("Polygon news fetch failed: %s", e)
    else:
        err = "polygon_key_missing"

    if not items:
        if getattr(settings, "news_allow_mock", False):
            from tools.polygon import _mock_news
            items = _mock_news()[:limit]
            source = "mock"
            logger.warning("Using mock news — NEWS_ALLOW_MOCK=true (dev only)")
        else:
            logger.warning(
                "No live news — returning empty feed (set POLYGON_API_KEY or NEWS_ALLOW_MOCK=true for dev)"
            )

    _cache.update({
        "items": items,
        "source": source,
        "expires": now + _NEWS_TTL,
        "error": err,
        "fetched_at": datetime.now(timezone.utc).isoformat(),
    })
    return items
