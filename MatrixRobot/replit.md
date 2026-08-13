# Matrix Robot — AI Trading Monitor

Mobile-first PWA dashboard for monitoring an autonomous LangGraph trading system on MT5. Iraqi Arabic-speaking user. Pure Agentic: LLM brain reasons via 15-tool registry.

## Run

- `pnpm --filter @workspace/api-server run dev` — Node API (port 8080)
- `pnpm --filter @workspace/dashboard run dev` — React frontend
- `bash artifacts/python-agents/start.sh` — Python agents (FastAPI, port 8000)
- `pnpm run typecheck` / `pnpm run build` — TS checks across all packages
- `pnpm --filter @workspace/api-spec run codegen` — regenerate API hooks + Zod from `lib/api-spec/openapi.yaml`

## Stack

- pnpm workspaces, Node 24, TS 5.9, Express 5, React + Vite + Tailwind + shadcn
- Python: FastAPI + LangGraph + LangChain (tool-calling Claude)
- Validation: Zod (`zod/v4`) + drizzle-zod, Orval codegen
- Market data: **Twelve Data** (Grow plan, 55 req/min). News falls back to mock (Grow lacks news endpoint).
- Symbols (24): 19 forex pairs + XAUUSD, XAGUSD, US30, US500, USTEC. Indices map to TD via `_INDEX_TO_TD` in `tools/twelve_data.py` (US30→DJI, US500→SPX, USTEC→NDX). Broker symbol names assume JustMarkets; verify against `mt5.symbol_info()` if a different broker.
- LLM: OpenRouter (`anthropic/claude-sonnet-4.5`) → OpenAI (`gpt-4o-mini`) → rule-based ensemble

## Layout

- `lib/api-spec/openapi.yaml` — API contract (source of truth — DO NOT hand-write types)
- `lib/api-client-react/src/generated/` — generated React Query hooks
- `lib/api-zod/src/generated/` — generated Zod schemas
- `artifacts/api-server/src/routes/{dashboard,agents,trading,sentiment}.ts` — Node routes (dashboard = mock; agents = proxy to Python; sentiment = Polygon, **still on Polygon**)
- `artifacts/dashboard/src/pages/dashboard.tsx` — main UI
- `artifacts/python-agents/main.py` — FastAPI entry
- `artifacts/python-agents/config.py` — pydantic-settings (all env vars)
- `artifacts/python-agents/agents/agentic_brain.py` — Claude tool-calling brain
- `artifacts/python-agents/tools/twelve_data.py` — market data client (drop-in for legacy `polygon.py`)
- `artifacts/python-agents/tools/registry.py` — 17 LangChain tools the brain calls (15 read-only analytics + `query_history` + `run_python_code`)
- `artifacts/python-agents/tools/sandbox.py` — sandboxed Python exec for the brain (numpy/pandas, 5s timeout, no I/O)
- `artifacts/python-agents/tools/memory.py` — Redis-or-dict store + `log_brain_decision` / `get_recent_decisions` / `log_trade_outcome` / `get_recent_outcomes`
- `artifacts/python-agents/agents/{data,risk,execution,sentiment}_agent.py` — pipeline nodes
- `artifacts/python-agents/backtest/engine.py` — deterministic ensemble replay (no LLM, ICT in `backtest_mode=True` so wall-clock killzones don't bias results)
- `artifacts/python-agents/routes/backtest.py` — `POST /agents/backtest/run` (single symbol) + `/agents/backtest/portfolio` (basket; aggregates exact gross win/loss R)
- `artifacts/python-agents/mt5_windows_bridge.py` — runs on user's Windows PC

## Architecture decisions

- **Contract-first OpenAPI**: always run codegen after editing `openapi.yaml` before touching frontend/backend types
- **Mock dashboard data**: `dashboard.ts` returns in-memory simulated values. Replace with real service calls when wiring full backend.
- **PAPER_MODE default**: only flip to `ACTIVE` after MT5 bridge confirmed
- **30s polling** from frontend, no WebSocket
- **MT5 Windows-only**: user runs `mt5_windows_bridge.py` on their PC; Replit connects via `MT5_BRIDGE_URL`
- **Pure Agentic**: LLM brain selects from 17-tool registry — 15 analytics (indicators, MTF, ICT, Wyckoff, Elliott, harmonic, volume profile, chart patterns, vol regime, sentiment, calendar, correlation, prop_status, quote, universe_snapshot) + `query_history` (self-recall: past decisions + closed-trade outcomes from `memory.py`) + `run_python_code` (sandboxed numpy/pandas, 5s timeout, no I/O — for bespoke metrics no pre-built tool covers). Brain decisions auto-logged via `memory.log_brain_decision` after each cycle so next cycle's `query_history` works. Falls back to deterministic ensemble when no LLM key.

## Product (mobile-first monitor)

- System online/offline, trading state (Paper/Active/Frozen) with confirmations
- Connection tiles: Polygon, Redis, MT5
- Balance / Equity / Daily DD / Total DD with alert banners near 2.5% daily / 8% total
- Market news with impact tag, agent decision log, live positions, controls (mode switch + auto-cycle scheduler)

## User preferences

- **User is male (ذكر) — always use masculine Arabic forms (أنت، تفعل، رأيت...) NOT feminine**
- Mobile browser only (no app)
- UI labels English (user reads Arabic, technical terms English)
- No emojis in UI
- Default PAPER_MODE; never activate live without manual confirmation
- Risk limits configurable: daily 2.5%, total 8%
- Communicate **in Arabic** in chat (masculine forms)

## Secrets

| Key | Status |
|-----|--------|
| `TWELVE_DATA_API_KEY` | ✓ active (Grow plan) |
| `POLYGON_API_KEY` | legacy — still used by Node sentiment route |
| `OPENROUTER_API_KEY` | ✓ active (Claude Sonnet 4.5) |
| `OPENAI_API_KEY` | ✓ active (fallback) |
| `GEMINI_API_KEY` / `GOOGLE_API_KEY` | available |
| `SESSION_SECRET` | ✓ |
| `MT5_LOGIN` / `MT5_PASSWORD` / `MT5_SERVER` | ✓ — credentials in `.env` on VPS only; bridge attaches to running terminal so login args are fallback only |
| `MT5_BRIDGE_URL` | ✓ active — `http://YOUR_VPS_IP:5555` (Windows Server bridge, direct) |
| `MT5_BRIDGE_SECRET` | ✓ set on both Replit + VPS `.env` |

## MT5 setup (user-side, pending)

Download links served by api-server:
- `GET /api/download/mt5-bridge` → `mt5_windows_bridge.py`
- `GET /api/download/mt5-bat` → `START_MT5_BRIDGE.bat`
- `GET /api/download/mt5-env` → pre-filled `.env`

Steps for user's Windows laptop: download both files → put in `Desktop\MatrixRobot\` → create `.env` with MT5 creds → install MT5 Desktop and log in → run `START_MT5_BRIDGE.bat` → `ipconfig` for IPv4 → add `MT5_BRIDGE_URL=http://<ip>:5555` to Replit Secrets → restart Python service.

## Python agent routes (`/agents/*`)

`health`, `info`, `cycle/run`, `cycle/status`, `signals`, `state`, `positions`, `mode` (GET/POST), `scheduler/{status,start,stop}`, `positions/live`, `analytics`, `prop-status`, `backtest/run`, `backtest/portfolio`.

Node bridge `artifacts/api-server/src/routes/agents.ts` proxies `/api/agents/*` to Python.

## FundedNext compliance (`tools/prop_rules.py` + `tools/account_state.py`)

Internal stricter caps (bot self-halts BEFORE FN hard caps):
- `MAX_DAILY_DRAWDOWN_PCT=4.0` (FN cap 5%), `MAX_TOTAL_DRAWDOWN_PCT=9.0` (FN cap 10%)
- `MAX_RISK_PER_TRADE_PCT=0.8`, `MAX_TOTAL_OPEN_RISK_PCT=3.0`, `MAX_CONCURRENT_POSITIONS=5`
- `PROP_MIN_TRADING_DAYS=5`, `PROP_CONSISTENCY_MAX_DAY_SHARE_PCT=40.0`
- Plan: Stellar 2-Step, phases `PHASE_1|PHASE_2|FUNDED`

**Mandatory safety (paper + live):**
- `require_stop_loss=True` — every order has SL (≥15 pips). Execution agent rejects naked orders.
- `max_trades_per_day=20` — hard cap counted at OPEN, resets at broker/FundedNext server midnight
- `min_position_hold_seconds=60` — both close routes reject closes if age <60s (anti-scalping)

**`compute_safe_sizing()`** (shared by risk + execution agents): SL = 1.5×ATR (min 15 pips), TP = 2×SL. Lots derived so max loss respects all 4 caps simultaneously (per-trade, daily DD room, total DD room, portfolio room), with `sizing_safety_buffer_pct=0.3`. Strict budget contract — rejects when no room.

`GET /agents/prop-status` exposes live compliance snapshot. `account_state.reset_for_new_challenge()` wipes for Phase 2 / fresh eval.

## Analytics layer (advanced)

- **Indicators** (`tools/indicators.py`): RSI, MACD, Stoch K/D, Williams %R, ADX+DI±, EMA200, Ichimoku, Pivots R1-S2, S/R, Fib, BB-width
- **MTF** (`tools/multi_timeframe.py`): M15/H1/H4/D1 consensus, `bullish`/`bearish` only when ≥3 of 4 align
- **Correlation guard** (`tools/correlation.py`): blocks adding to same-direction exposure in same group
- **Volatility regime** (`tools/volatility_regime.py`): ATR percentile → size multiplier (1.20/1.00/0.60)
- **Economic calendar** (`tools/economic_calendar.py`): internal weekly schedule, blocks trades during HIGH events
- **ICT/SMC** (`tools/ict_smc.py`): swing highs/lows, BOS, CHoCH, order blocks, FVG, liquidity pools, premium/discount, killzones (Asian/London/NY, 1.15× amplifier). Ensemble weight 3.5 (heaviest).
- **Five strategy tools**: Wyckoff, Elliott, harmonic, volume profile, chart patterns

`GET /agents/analytics` returns full snapshot per cycle.

## Sentiment (Node)

`artifacts/api-server/src/services/sentiment.ts` + `routes/sentiment.ts`: Polygon news + GPT-4o-mini classification (BULLISH/BEARISH/NEUTRAL + confidence). 5-min cache. Falls back to demo when keys missing. **Still on Polygon** — migrate to Twelve Data later.

## Gotchas

- Run codegen after every `openapi.yaml` change before touching types
- `dashboard.ts` mock data resets on API restart
- Sentiment cache = 5 min (avoids Polygon rate limits)
- `@lru_cache` on `get_settings()` → Python service MUST fully restart to pick up new env vars
- Polygon free tier: forex snapshot returns 403, news rate-limits to ~5/min
- Twelve Data Grow plan has no news endpoint → `fetch_news` returns mocks
- **Twelve Data + Node**: api-server uses `node:https` (not `fetch`) with `User-Agent: python-httpx/0.27.0` — TD's WAF rejects undici's default headers with a misleading "incorrect apikey" 401 (`services/twelve_data.ts` `httpsGetJson`). Python httpx works unchanged.
- `MT5_BRIDGE_URL` unset = MT5 tile red (normal until user runs Windows bridge)
- **MT5 Market-Execution gotcha**: MetaQuotes-Demo and most prop accounts silently drop `sl`/`tp` on `TRADE_ACTION_DEAL`. Bridge v1.4.0+ fixes via follow-up `TRADE_ACTION_SLTP`. Bridges <1.4.0 open trades WITHOUT stops — user must redownload.
- "Python Agent Service" duplicate workflow fails on port collision — only "Python Agents (FastAPI)" runs.
- Never write API keys to chat — use `requestEnvVar` / `setEnvVars`.

## Pointers

- See the `pnpm-workspace` skill for workspace structure, TS setup, package details
- See `environment-secrets` skill before touching secrets
