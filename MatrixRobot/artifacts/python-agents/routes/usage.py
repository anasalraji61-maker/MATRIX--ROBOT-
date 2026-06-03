import httpx
from fastapi import APIRouter
from config import get_settings

router = APIRouter()


@router.get("/usage/openrouter")
async def openrouter_usage():
    settings = get_settings()
    key = settings.effective_openrouter_key
    if not key:
        return {"available": False}

    try:
        async with httpx.AsyncClient(timeout=8.0) as client:
            resp = await client.get(
                "https://openrouter.ai/api/v1/auth/key",
                headers={"Authorization": f"Bearer {key}"},
            )
            if resp.status_code != 200:
                return {"available": False}
            data = resp.json().get("data", {})
            usage = data.get("usage")
            if not isinstance(usage, (int, float)):
                return {"available": False}
            return {
                "available": True,
                "usage_usd": round(usage, 6),
                "limit": data.get("limit"),
            }
    except Exception:
        return {"available": False}
