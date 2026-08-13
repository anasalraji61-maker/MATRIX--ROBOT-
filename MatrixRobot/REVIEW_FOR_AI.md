# Matrix Robot — Project Review Pack (Complete)

> **Purpose:** Full source snapshot for external AI review (ChatGPT, Gemini, etc.)
> **Date:** June 2026 | **Version:** Phase 5 + **Phase 6** (latest code — includes all ChatGPT fixes)

---

## What Is This?

**Matrix Robot** is a multi-agent AI trading system for Forex, Gold (XAUUSD), indices, and stocks.
It runs on a Windows VPS with MetaTrader 5 via a local HTTP bridge.

### Architecture

```
MetaTrader 5  ←→  MT5 Bridge (:5555)  ←→  Python Brain (FastAPI :8000)
                                              LangGraph multi-agent pipeline
                                              ↓
                                         Claude (OpenRouter) — decisions
                                         Polygon — live news
                                         FinBERT/GPT — sentiment
                                         Twelve Data — quotes/OHLC
                                         Supabase/Postgres — memory, trades
                                         Telegram — alerts
```

### Agent Pipeline (LangGraph)

```
emergency_guard → position_manager → data_fetch → sentiment → analysis →
risk (per-trade batch) → supervisor → execution
```

---

## Phase 6 — Professional Hardening (NEW in this pack)

| Fix | File(s) |
|-----|---------|
| FundedNext **server timezone** (not UTC daily reset) | `tools/prop_time.py`, `account_state.py`, `prop_rules.py`, `emergency_guard.py` |
| **ACTIVE fail-closed** on mock/stale quotes, bars, news | `tools/data_quality.py`, `twelve_data.py`, `data_agent.py` |
| **Emergency fail-closed** when account unavailable | `tools/emergency_guard.py` |
| **SELL trailing stop** bug fix | `tools/position_manager.py` |
| **SL/TP verify** after open + rollback | `tools/mt5_bridge.py` |
| **Per-trade risk** (`approved_risk_trades[]`) | `tools/risk_batch.py`, `agents/risk_agent.py` |
| **Challenge vs Funded** news rules | `tools/prop_rules.py` |
| **Qualified trades** counter (min 5) | `tools/account_state.py`, `tools/close_logger.py` |
| Tests | `tests/test_phase6_hardening.py` |

---

## Phase 5 — Intraday Adaptive

- Session engine (ICT killzones), adaptive scheduler 45/60/90 min
- Position manager: 8h max hold, breakeven @1R, trailing @1.5R
- Liquidity/spread guard

---

## Key Files for Review

```
artifacts/python-agents/tools/prop_time.py
artifacts/python-agents/tools/data_quality.py
artifacts/python-agents/tools/risk_batch.py
artifacts/python-agents/tools/risk_sizing.py
artifacts/python-agents/tools/prop_rules.py
artifacts/python-agents/tools/emergency_guard.py
artifacts/python-agents/tools/position_manager.py
artifacts/python-agents/tools/mt5_bridge.py
artifacts/python-agents/agents/graph.py
artifacts/python-agents/agents/execution_agent.py
artifacts/python-agents/config.py
```

---

## Production Settings (VPS)

| Setting | Value |
|---------|-------|
| Account | FundedNext Demo (bridge :5555) |
| News | Polygon (real headlines) |
| XAUUSD pip value | 10.0 (lot sizing fix) |
| Daily DD / Total DD | 4% / 9% internal |
| PROP_SERVER_UTC_OFFSET_HOURS | 3 (default) |

---

## What We Want Reviewers To Evaluate

1. Did **Phase 6** fix the prior critical issues (UTC reset, mock data, SELL trail, per-trade risk)?
2. What remains before **real Funded Challenge**?
3. Any **bugs** in Phase 6 code?
4. ML filter: ready for `enforce` mode?
5. Session killzones: too restrictive?

---

## Excluded (security / size)

- `.env` (real keys) — use `.env.example`
- `node_modules/`, `.venv/`, `__pycache__/`
- Binary executables

---

## Tests

```bash
cd artifacts/python-agents
python -m pytest tests/ -q
```

Key: `test_phase6_hardening.py`, `test_risk_sizing.py`, `test_session_engine.py`
