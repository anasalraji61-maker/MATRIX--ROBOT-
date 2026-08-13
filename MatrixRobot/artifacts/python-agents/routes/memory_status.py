"""Postgres / pgvector / Supabase connection status."""
from fastapi import APIRouter
from config import get_settings
from tools import memory
from tools.db_bootstrap import is_ready

router = APIRouter()


@router.get("/memory/status")
async def memory_status():
    s = get_settings()
    return {
        "database_configured": s.has_database,
        "postgres_connected": memory.is_postgres_connected(),
        "schema_ready": is_ready(),
        "redis_connected": memory.is_redis_connected(),
        "semantic_memory": "pgvector on semantic_memories table",
        "recommendation": (
            "Set DATABASE_URL in .env to your Supabase connection string "
            "(Project Settings → Database → URI). Enable vector extension in SQL Editor."
        ),
    }
