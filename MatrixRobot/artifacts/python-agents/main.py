"""
Matrix Robot — Python Agent Service
FastAPI application exposing the LangGraph multi-agent trading system.

All routes are prefixed with /agents so the shared reverse proxy can route
traffic correctly alongside the Node.js API server at /api.
"""
import hmac
import logging
import time
from collections import defaultdict
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.requests import Request

from config import get_settings
from agents.graph import get_graph
from routes.health import router as health_router
from routes.cycle import router as cycle_router
from routes.state import router as state_router
from routes.trading import router as trading_router
from routes.accounts import router as accounts_router
from routes.backtest import router as backtest_router
from routes.usage import router as usage_router
from routes.strategy import router as strategy_router
from routes.pnl import router as pnl_router

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("matrix.agents")


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    logger.info("Matrix Robot Agent Service starting...")
    logger.info(f"Mode: {settings.trading_state}")
    logger.info(f"LLM: {'OpenRouter' if settings.effective_openrouter_key else 'OpenAI' if settings.effective_openai_key else 'Rule-based (no LLM key)'}")
    logger.info(f"Polygon: {'connected' if settings.has_polygon else 'mock data'}")
    logger.info(f"MT5 Bridge: {settings.mt5_bridge_url or 'not configured'}")
    logger.info(f"MT5 Native: {'configured' if settings.has_mt5 else 'not configured'}")
    logger.info(f"Redis: {'connected' if settings.has_redis else 'in-memory fallback'}")
    logger.info(f"Symbols: {', '.join(settings.symbol_list)}")

    # Pre-compile the LangGraph at startup to avoid cold-start on first request
    get_graph()
    logger.info("LangGraph compiled and ready")

    # Restore persistent runtime state: trading mode + scheduler
    import runtime_state
    from routes.trading import get_effective_mode, _scheduler_loop
    import asyncio
    from routes import trading as trading_module

    saved_mode = runtime_state.get_mode()
    if saved_mode:
        logger.info(f"Restored trading mode from persistent state: {saved_mode}")

    sched = runtime_state.get_scheduler()
    if settings.disable_scheduler:
        logger.info("Scheduler disabled (DISABLE_SCHEDULER=true) — proxy-only mode, VPS brain runs cycles")
    elif sched.get("running") and sched.get("interval_minutes"):
        interval = int(sched["interval_minutes"])
        trading_module._scheduler_interval_minutes = interval
        trading_module._scheduler_running = True
        trading_module._scheduler_task = asyncio.create_task(_scheduler_loop(interval))
        logger.info(f"Auto-restored scheduler — every {interval} min (effective mode: {get_effective_mode()})")

    yield

    logger.info("Agent service shutting down")


# ── Simple in-memory rate limiter ─────────────────────────────────────────────
_rate_hits: dict = defaultdict(list)
# (max_requests, window_seconds) per endpoint
_RATE_LIMITS: dict = {
    "/agents/cycle/run":      (5,  60),
    "/agents/mode":           (10, 60),
    "/agents/scheduler/start":(10, 60),
    "/agents/scheduler/stop": (10, 60),
}


def _build_allowed_origins(settings) -> list[str]:
    """Return CORS allow-list. Falls back to localhost-only when not configured."""
    if settings.allowed_origins:
        return [o.strip() for o in settings.allowed_origins.split(",") if o.strip()]
    return [
        "http://localhost",
        "http://localhost:3000",
        "http://localhost:5173",
        "http://127.0.0.1",
        "http://127.0.0.1:3000",
        "http://127.0.0.1:5173",
    ]


_settings = get_settings()

app = FastAPI(
    title="Matrix Robot — Agent Service",
    description=(
        "LangGraph multi-agent trading system powering Matrix Robot. "
        "Agents: Data → Sentiment → Analysis → Risk → Supervisor → Execution"
    ),
    version="1.0.0",
    lifespan=lifespan,
    docs_url="/agents/docs" if _settings.debug_docs else None,
    redoc_url="/agents/redoc" if _settings.debug_docs else None,
    openapi_url="/agents/openapi.json" if _settings.debug_docs else None,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=_build_allowed_origins(_settings),
    allow_credentials=True,
    allow_methods=["GET", "POST", "DELETE"],
    allow_headers=["Content-Type", "X-Brain-Secret"],
)


@app.middleware("http")
async def api_secret_guard(request: Request, call_next):
    """Require X-Brain-Secret header for all state-changing requests.

    Behavior:
    - If MT5_BRIDGE_SECRET is configured: enforces the secret (fail-closed on mismatch).
    - If MT5_BRIDGE_SECRET is NOT configured: logs a startup warning and STILL blocks
      write requests with a 401 so the system is never silently open.
      Set MT5_BRIDGE_SECRET in Replit Secrets to unlock write access.
    """
    settings = get_settings()
    secret = settings.mt5_bridge_secret

    if request.method in ("POST", "DELETE", "PUT", "PATCH"):
        # Health endpoint is always open
        if request.url.path.rstrip("/") != "/agents/health":
            if not secret:
                # Fail-closed: no secret configured → reject all writes
                logger.warning(
                    "SECURITY: write request blocked — MT5_BRIDGE_SECRET not configured. "
                    "Set it in Replit Secrets to enable write operations."
                )
                return JSONResponse(
                    {"error": "Write operations disabled — MT5_BRIDGE_SECRET not configured on server"},
                    status_code=401,
                )
            provided = request.headers.get("X-Brain-Secret", "")
            try:
                match = hmac.compare_digest(provided.encode(), secret.encode())
            except Exception:
                match = False
            if not match:
                return JSONResponse(
                    {"error": "Unauthorized — missing or invalid X-Brain-Secret"},
                    status_code=401,
                )
    return await call_next(request)


@app.middleware("http")
async def rate_limiter(request: Request, call_next):
    """Simple per-IP rate limiter for expensive write endpoints."""
    path = request.url.path
    method = request.method
    if method == "POST" and path in _RATE_LIMITS:
        limit, window = _RATE_LIMITS[path]
        client_ip = (request.client.host if request.client else "unknown")
        key = f"{client_ip}:{path}"
        now = time.time()
        hits = [t for t in _rate_hits[key] if now - t < window]
        if len(hits) >= limit:
            return JSONResponse(
                {"error": f"Rate limit exceeded — max {limit} requests per {window}s"},
                status_code=429,
            )
        hits.append(now)
        _rate_hits[key] = hits
    return await call_next(request)

PREFIX = "/agents"
app.include_router(health_router, prefix=PREFIX, tags=["Health"])
app.include_router(cycle_router, prefix=PREFIX, tags=["Cycle"])
app.include_router(state_router, prefix=PREFIX, tags=["State"])
app.include_router(trading_router, prefix=PREFIX, tags=["Trading"])
app.include_router(accounts_router, prefix=PREFIX, tags=["Accounts"])
app.include_router(backtest_router, prefix=PREFIX, tags=["Backtest"])
app.include_router(usage_router, prefix=PREFIX, tags=["Usage"])
app.include_router(strategy_router, prefix=PREFIX, tags=["Strategy"])
app.include_router(pnl_router, prefix=PREFIX, tags=["PnL"])


@app.get(PREFIX + "/info")
async def info():
    settings = get_settings()
    from routes.trading import get_effective_mode
    return {
        "name": "Matrix Robot Agent Service",
        "version": "1.0.0",
        "mode": get_effective_mode(),
        "symbols": settings.symbol_list,
        "risk_limits": {
            "daily_drawdown_pct": settings.max_daily_drawdown_pct,
            "total_drawdown_pct": settings.max_total_drawdown_pct,
            "max_risk_per_trade_pct": settings.max_risk_per_trade_pct,
        },
        "agents": [
            "Data Agent (Polygon.io)",
            "Sentiment Agent (FinBERT)",
            "Analysis Agent (pandas-ta + LLM)",
            "Risk Agent (Kelly Criterion)",
            "Supervisor Agent (LLM decision)",
            "Execution Agent (MT5 bridge)",
        ],
        "llm": {
            "openrouter": bool(settings.effective_openrouter_key),
            "openai": bool(settings.effective_openai_key),
            "model": settings.primary_model if settings.has_llm else "rule-based",
        },
        "mt5": {
            "bridge_url": bool(settings.mt5_bridge_url),
            "native": settings.has_mt5,
        },
    }
