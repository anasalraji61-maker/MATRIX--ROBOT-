"""Semantic memory — pgvector on Supabase/Postgres for similar news & cycle context."""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any

import httpx

from config import get_settings

logger = logging.getLogger("matrix.semantic")

_OPENROUTER_EMBED = "https://openrouter.ai/api/v1/embeddings"


async def embed_text(text: str) -> list[float] | None:
    s = get_settings()
    key = s.effective_openrouter_key
    if not key or not text.strip():
        return None
    try:
        async with httpx.AsyncClient(timeout=25.0) as client:
            r = await client.post(
                _OPENROUTER_EMBED,
                headers={
                    "Authorization": f"Bearer {key}",
                    "Content-Type": "application/json",
                    "HTTP-Referer": "https://matrix-robot.local",
                    "X-Title": "Matrix Robot Embeddings",
                },
                json={
                    "model": s.embedding_model,
                    "input": text[:8000],
                },
            )
        if r.status_code != 200:
            logger.warning("Embedding HTTP %s", r.status_code)
            return None
        data = r.json()
        emb = data["data"][0]["embedding"]
        if not isinstance(emb, list):
            return None
        return [float(x) for x in emb]
    except Exception as e:
        logger.warning("Embedding failed: %s", e)
        return None


def _vec_literal(vec: list[float]) -> str:
    return "[" + ",".join(f"{x:.8f}" for x in vec) + "]"


async def store(
    kind: str,
    content: str,
    *,
    symbol: str | None = None,
    metadata: dict | None = None,
) -> bool:
    from tools.memory import _get_pg_pool

    pool = _get_pg_pool()
    if pool is None or not content.strip():
        return False

    emb = await embed_text(content)
    if not emb:
        return False

    raw = dict(metadata or {})
    raw["ts"] = datetime.now(timezone.utc).isoformat()
    try:
        with pool.connection() as conn:
            conn.execute(
                """
                INSERT INTO semantic_memories (kind, symbol, content, embedding, raw)
                VALUES (%s, %s, %s, %s::vector, %s::jsonb)
                """,
                (
                    kind,
                    (symbol or "").upper() or None,
                    content[:4000],
                    _vec_literal(emb),
                    json.dumps(raw, default=str),
                ),
            )
        return True
    except Exception as e:
        logger.warning("semantic store failed: %s", e)
        return False


async def search_similar(
    query: str,
    *,
    kind: str | None = None,
    limit: int = 3,
) -> list[dict[str, Any]]:
    from tools.memory import _get_pg_pool

    pool = _get_pg_pool()
    if pool is None or not query.strip():
        return []

    emb = await embed_text(query)
    if not emb:
        return []

    lit = _vec_literal(emb)
    try:
        with pool.connection() as conn:
            if kind:
                cur = conn.execute(
                    """
                    SELECT content, raw, kind, symbol,
                           1 - (embedding <=> %s::vector) AS similarity
                    FROM semantic_memories
                    WHERE kind = %s AND embedding IS NOT NULL
                    ORDER BY embedding <=> %s::vector
                    LIMIT %s
                    """,
                    (lit, kind, lit, int(limit)),
                )
            else:
                cur = conn.execute(
                    """
                    SELECT content, raw, kind, symbol,
                           1 - (embedding <=> %s::vector) AS similarity
                    FROM semantic_memories
                    WHERE embedding IS NOT NULL
                    ORDER BY embedding <=> %s::vector
                    LIMIT %s
                    """,
                    (lit, lit, int(limit)),
                )
            rows = cur.fetchall()
        out = []
        for row in rows:
            if row[4] and float(row[4]) < 0.55:
                continue
            out.append({
                "content": row[0],
                "raw": row[1],
                "kind": row[2],
                "symbol": row[3],
                "similarity": round(float(row[4]), 3) if row[4] is not None else 0,
            })
        return out
    except Exception as e:
        logger.warning("semantic search failed: %s", e)
        return []


def format_similar_context(matches: list[dict]) -> str:
    if not matches:
        return ""
    lines = ["Similar past context (pgvector):"]
    for i, m in enumerate(matches, 1):
        sim = m.get("similarity", 0)
        kind = m.get("kind", "")
        snippet = (m.get("content") or "")[:280]
        lines.append(f"{i}. [{kind}] sim={sim:.2f} — {snippet}")
    return "\n".join(lines)
