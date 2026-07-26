"""Create Postgres / Supabase schema (tables + pgvector) on Brain startup."""
from __future__ import annotations

import logging

logger = logging.getLogger("matrix.db_bootstrap")

_DDL = """
CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS kv_store (
    key TEXT PRIMARY KEY,
    value JSONB NOT NULL,
    expires_at TIMESTAMPTZ
);

CREATE TABLE IF NOT EXISTS brain_decisions (
    id BIGSERIAL PRIMARY KEY,
    ts TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    symbol TEXT NOT NULL,
    signal TEXT,
    strength DOUBLE PRECISION,
    reasons JSONB,
    llm_analysis TEXT,
    source TEXT,
    raw JSONB NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_brain_decisions_symbol_ts ON brain_decisions (symbol, ts DESC);

CREATE TABLE IF NOT EXISTS trade_outcomes (
    id BIGSERIAL PRIMARY KEY,
    ts TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    ticket BIGINT,
    symbol TEXT NOT NULL,
    side TEXT,
    entry DOUBLE PRECISION,
    exit DOUBLE PRECISION,
    volume DOUBLE PRECISION,
    pnl DOUBLE PRECISION,
    reason TEXT,
    raw JSONB NOT NULL
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_trade_outcomes_ticket ON trade_outcomes (ticket) WHERE ticket IS NOT NULL;

CREATE TABLE IF NOT EXISTS cycle_logs (
    cycle_id TEXT PRIMARY KEY,
    started_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    finished_at TIMESTAMPTZ,
    status TEXT,
    mode TEXT,
    symbols_analyzed JSONB,
    decision JSONB,
    raw JSONB NOT NULL
);

CREATE TABLE IF NOT EXISTS drawdown_snapshots (
    id BIGSERIAL PRIMARY KEY,
    ts TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    balance DOUBLE PRECISION,
    equity DOUBLE PRECISION,
    daily_dd_pct DOUBLE PRECISION,
    total_dd_pct DOUBLE PRECISION,
    open_positions INT,
    open_risk_pct DOUBLE PRECISION,
    margin_used_pct DOUBLE PRECISION,
    raw JSONB NOT NULL
);

CREATE TABLE IF NOT EXISTS semantic_memories (
    id BIGSERIAL PRIMARY KEY,
    ts TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    kind TEXT NOT NULL,
    symbol TEXT,
    content TEXT NOT NULL,
    embedding vector(1536),
    raw JSONB
);
CREATE INDEX IF NOT EXISTS idx_semantic_memories_kind_ts ON semantic_memories (kind, ts DESC);

CREATE TABLE IF NOT EXISTS strategy_scores (
    id BIGSERIAL PRIMARY KEY,
    strategy TEXT NOT NULL,
    symbol TEXT NOT NULL,
    regime TEXT,
    signal TEXT,
    confidence DOUBLE PRECISION,
    outcome TEXT,
    pnl DOUBLE PRECISION,
    ts TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_strategy_scores_symbol_ts ON strategy_scores (symbol, ts DESC);
CREATE INDEX IF NOT EXISTS idx_strategy_scores_outcome ON strategy_scores (outcome) WHERE outcome IS NOT NULL;
"""


def ensure_schema() -> bool:
    """Run DDL if DATABASE_URL / Postgres pool is available."""
    from tools.memory import _get_pg_pool, has_postgres

    pool = _get_pg_pool()
    if pool is None:
        return False
    try:
        with pool.connection() as conn:
            conn.execute(_DDL)
        logger.info("Postgres schema ready (Supabase/pgvector)")
        return True
    except Exception as e:
        logger.warning("Postgres schema bootstrap failed: %s", e)
        return False


def is_ready() -> bool:
    from tools.memory import has_postgres
    return has_postgres()
