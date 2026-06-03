"""
Agentic Brain — replaces the hard-coded analysis_agent.

The brain is an LLM (Claude 3.5 / GPT-4o-mini via OpenRouter) given a
registry of read-only tools and asked to:
  1. Scan the universe via `universe_snapshot`
  2. Drill into 1–3 promising symbols with the analytical tools of its choice
  3. Emit a JSON list of trade proposals, one per symbol it analyzed

The output is the SAME schema (`AnalysisResult` list under state["analyses"])
the old analysis_agent produced — so risk_agent + execution_agent + the
dashboard work unchanged.

Fallback chain:
  • LLM tool-calling brain  → primary
  • LLM single-shot (no tools, old analysis_agent) → if tool binding fails
  • Rule-based ensemble (analysis_agent's _ensemble path) → if no LLM key

FN compliance is NEVER decided by the brain. The brain proposes; risk_agent
and execution_agent always have the final veto.
"""
from __future__ import annotations
import json
import logging
from typing import Any

from config import get_settings
from models.schemas import AnalysisResult
from tools.registry import build_tools
from tools import memory as _memory

logger = logging.getLogger("matrix.brain")

SYSTEM_PROMPT_TEMPLATE = """You are the Matrix Robot trading brain — an autonomous research analyst
operating under a FundedNext Stellar 2-Step prop-firm challenge.

═══════════════════════════════════════════════════════════════
TOOL REGISTRY (use in this preferred order each cycle)
═══════════════════════════════════════════════════════════════
STEP 0 — Policy check (ALWAYS FIRST):
  • `get_adaptive_policy()` — read your current APE state: active risk cuts,
    paused symbols, conviction overrides. Do this BEFORE scanning the universe.

STEP 1 — Universe scan:
  • `universe_snapshot()` — one-line overview of all 24 symbols.

STEP 2 — Deep analysis on 1–3 promising symbols:
  • `get_indicators(symbol)` — RSI, MACD, ATR, EMAs, Bollinger, Stoch, ADX…
  • `get_mtf_consensus(symbol)` — M15/H1/H4/D1 alignment
  • `get_ict_smc(symbol)` — BOS, CHoCH, order blocks, FVG, liquidity, killzones
  • `get_wyckoff(symbol)` — ACCUMULATION / MARKUP / DISTRIBUTION / MARKDOWN
  • `get_elliott_wave(symbol)` — wave count + expected next leg
  • `get_harmonic_pattern(symbol)` — Gartley, Bat, Butterfly, Crab, Cypher PRZ
  • `get_volume_profile(symbol)` — POC, VAH/VAL, HVN/LVN
  • `get_chart_pattern(symbol)` — double top/bottom, H&S, triangles, wedges
  • `get_volatility_regime(symbol)` — low/normal/high + size multiplier
  • `get_market_sentiment()` — news backdrop (BULLISH/BEARISH/NEUTRAL)
  • `get_economic_calendar()` — upcoming HIGH-impact events + blackout status
  • `get_correlation_report()` — exposure groups + blocked directions
  • `get_quote(symbol)` — current bid/ask/mid

STEP 3 — Self-check before deciding:
  • `query_history(symbol)` — your OWN past decisions + trade outcomes on this
    symbol. Strongly recommended before any BUY/SELL to avoid flip-flopping
    and to learn from prior losses.
  • `get_prop_status()` — FundedNext compliance snapshot. If can_trade=false,
    EVERY symbol must be HOLD. Always call this before finalizing.

STEP 4 — Adaptive policy (when conditions warrant):
  • `apply_adaptive_change(...)` — apply a DEFENSIVE adaptation autonomously.
    See ADAPTIVE POLICY section below.

POWER tool (use sparingly):
  • `run_python_code(code)` — sandboxed numpy/pandas, 5s limit, no I/O.
    Use for bespoke metrics no pre-built tool covers.

═══════════════════════════════════════════════════════════════
ADAPTIVE POLICY ENVELOPE (APE) — YOUR AUTONOMOUS AUTHORITY
═══════════════════════════════════════════════════════════════
You may autonomously apply these DEFENSIVE changes without human approval:

  REDUCE_RISK        — cut position sizes. value="0.5" = half normal size.
                      Min allowed: 0.3 (30% of normal). Cannot exceed 1.0.
  RESET_RISK         — restore to baseline when conditions improve.
  PAUSE_SYMBOL       — stop trading a symbol. value="EURUSD". Max 24h.
  RESUME_SYMBOL      — un-pause a symbol when you see recovery.
  TIGHTEN_CONVICTION — raise entry threshold. value="0.75". Range 0.55–0.85.
  RESET_CONVICTION   — restore default conviction threshold.
  SKIP_SESSION       — skip THIS cycle entirely (no trades opened).

WHEN TO USE APE (use good judgement):
  After 2+ consecutive losses on same symbol → PAUSE_SYMBOL or REDUCE_RISK
  After 3+ consecutive losses overall → REDUCE_RISK to 0.5 or lower
  Extreme spread or low-liquidity session → SKIP_SESSION
  Mixed/contradictory signals across all tools → TIGHTEN_CONVICTION
  Approaching daily DD limit (≥3%) → REDUCE_RISK aggressively
  Symbol showing systematic bad performance → PAUSE_SYMBOL for 12-24h
  Conditions recover (win streak, clear structure) → RESET_RISK / RESET_CONVICTION

ALWAYS include in apply_adaptive_change:
  reason            — cite SPECIFIC data ("RSI=78, MTF=bearish 3/4, last 2 trades lost $X")
  expected_benefit  — what improves ("smaller loss if wrong, same upside if right")
  rollback_condition — when you WILL reset ("when RSI < 65 and MTF realigns bullish")
  trigger_summary   — brief data summary that triggered the decision

YOU MAY NOT (requires human approval — requests will be rejected):
  ✗ Increase risk above baseline
  ✗ Enable live trading
  ✗ Change drawdown limits
  ✗ Use HFT, Martingale, Grid, Copy Trading
  ✗ Change core strategy to scalping/HFT

═══════════════════════════════════════════════════════════════
FUNEDNEXT COMPLIANCE RULES (MANDATORY — NEVER VIOLATE)
═══════════════════════════════════════════════════════════════
  • Max 5% daily loss, 10% total drawdown (internal bot targets: 4% / 9%)
  • Min 60 seconds holding time per trade (already enforced — do NOT suggest
    strategies that require faster exits)
  • Max 20 trades per day [INTERNAL SAFETY CAP — not an official FundedNext rule;
    FN Stellar 2-Step has no maximum trade count, but HFT/hyperactivity is monitored.
    This cap prevents hyperactive behavior that could flag the account.]
  • No HFT / scalping strategies
  • No copy/mirror trading from other accounts
  • No Martingale, Grid, or toxic order flow patterns
  • No trading ±10 min around HIGH-impact news (calendar enforces this)
  • XAUUSD: leverage is 1:10 (since Jan 2026) — brain must NOT oversize XAUUSD
  • Consistent strategy family across challenge phases (TREND/SWING/ICT — no
    sudden style pivots that make the account look non-reproducible)
  • Margin usage must stay below 70% (internal target: 50%)

═══════════════════════════════════════════════════════════════
OUTPUT FORMAT
═══════════════════════════════════════════════════════════════
FINAL JSON (exact, no markdown, no code fences):
{"analyses":[{"symbol":"EURUSD","signal":"BUY","strength":0.72,"reasons":["..."],"llm_analysis":"one paragraph"}]}

signal: BUY | SELL | HOLD
strength: 0.0–1.0 (below 0.55 → HOLD, filtered downstream anyway)
reasons: MUST cite tools used ("ICT: bullish CHoCH in discount", "MTF: 4/4 bullish")
llm_analysis: one paragraph explaining your reasoning including any APE decisions

Rules:
  • signal=HOLD when evidence mixed, weak, or prop guard blocks.
  • Prefer confluence: multiple analytical schools agreeing.
  • Account profile: __PROFILE__. Be CONSERVATIVE on FN_CHALLENGE or FN_FUNDED.
  • Stop after 4–10 tool calls. Emit best judgement on partial evidence.
  • You analyze; you do NOT execute. risk_agent has final veto on all caps.
"""


def _empty_analysis(symbol: str, reason: str) -> AnalysisResult:
    return AnalysisResult(
        symbol=symbol, signal="HOLD", strength=0.0,
        reasons=[reason], indicators_summary="", source="brain-skip",
    )


async def run(state: dict) -> dict:
    settings = get_settings()
    symbols = state.get("symbols_analyzed", settings.symbol_list)

    # No LLM key → defer to legacy ensemble analysis_agent
    if not settings.has_llm:
        from agents import analysis_agent
        logger.info("No LLM key — falling back to ensemble analysis_agent")
        return await analysis_agent.run(state)

    try:
        analyses = await _agentic_loop(state, settings, symbols)
    except Exception as e:
        from tools import llm_circuit
        if llm_circuit.is_credit_or_auth_error(e):
            llm_circuit.trip_openrouter(f"agentic_brain: {e}")
        logger.exception("Agentic brain failed — falling back to ensemble")
        from agents import analysis_agent
        return await analysis_agent.run(state)

    # If the loop ran out of iterations / produced no valid JSON / parser
    # returned empty, the brain effectively said nothing. Fall back to the
    # deterministic ensemble so the cycle still produces an actionable
    # snapshot instead of silently emitting all-HOLD.
    actionable = [a for a in analyses if a.get("signal") in ("BUY", "SELL")]
    if not analyses or not actionable:
        logger.warning(
            f"Brain produced {len(analyses)} analyses, {len(actionable)} actionable "
            f"— falling back to ensemble"
        )
        from agents import analysis_agent
        return await analysis_agent.run(state)

    # Fill missing symbols with HOLD so downstream can still iterate
    seen = {a["symbol"] for a in analyses}
    for s in symbols:
        if s not in seen:
            analyses.append(_empty_analysis(s, "Brain skipped this symbol").model_dump())

    best = _pick_best(analyses)
    return {**state, "analyses": analyses, "best_analysis": best}


def _pick_best(analyses: list[dict]) -> dict:
    actionable = [a for a in analyses if a.get("signal") in ("BUY", "SELL")]
    if not actionable:
        return analyses[0] if analyses else {}
    return max(actionable, key=lambda a: a.get("strength", 0.0))


async def _agentic_loop(state: dict, settings, symbols: list[str]) -> list[dict]:
    from langchain_core.messages import SystemMessage, HumanMessage, AIMessage, ToolMessage

    # Pick LLM — prefer Claude Sonnet 4.5 via OpenRouter (primary),
    # then Gemini 2.5 Flash (free fallback), then OpenAI.
    from tools import llm_circuit
    if settings.effective_openrouter_key and llm_circuit.is_openrouter_available():
        from langchain_openai import ChatOpenAI
        llm = ChatOpenAI(
            model=settings.primary_model,
            openai_api_key=settings.effective_openrouter_key,
            openai_api_base="https://openrouter.ai/api/v1",
            temperature=0.1, max_tokens=1500,
            max_retries=0,
        )
        source = f"openrouter-{settings.primary_model.split('/')[-1]}"
    elif settings.effective_gemini_key:
        from langchain_google_genai import ChatGoogleGenerativeAI
        llm = ChatGoogleGenerativeAI(
            model=settings.gemini_model,
            google_api_key=settings.effective_gemini_key,
            temperature=0.1,
            max_output_tokens=1500,
        )
        source = f"gemini-{settings.gemini_model}"
    else:
        from langchain_openai import ChatOpenAI
        llm = ChatOpenAI(
            model="gpt-4o-mini",
            openai_api_key=settings.effective_openai_key,
            temperature=0.1, max_tokens=1500,
        )
        source = "openai-gpt4o-mini"

    tools = build_tools(state)
    llm_with_tools = llm.bind_tools(tools)
    tool_map = {t.name: t for t in tools}

    profile = getattr(settings, "account_profile", "FN_CHALLENGE")
    sys = SYSTEM_PROMPT_TEMPLATE.replace("__PROFILE__", profile)
    user = (
        f"Universe ({len(symbols)} symbols): {', '.join(symbols)}\n"
        f"Account profile: {getattr(settings, 'account_profile', 'FN_CHALLENGE')}\n"
        f"Trading mode: {state.get('mode', settings.trading_state)}\n"
        f"Start with universe_snapshot, then drill into the 1-3 most actionable."
    )
    messages = [SystemMessage(content=sys), HumanMessage(content=user)]

    MAX_ITERS = 12  # snapshot + drill 1-3 symbols × 2-4 tools + history/python + prop_status + final
    FORCE_FINAL_AT = MAX_ITERS - 1  # penultimate: stop offering tools, demand JSON
    final_text = ""
    for it in range(MAX_ITERS):
        if it >= FORCE_FINAL_AT:
            # Last turn: invoke WITHOUT tools and prepend a forcing instruction so
            # the model is obligated to emit the FINAL JSON on whatever it has.
            messages.append(HumanMessage(content=(
                "Time's up. Emit the FINAL JSON now based on the evidence "
                "you already gathered. Do not call any more tools."
            )))
            resp = await llm.ainvoke(messages)
            messages.append(resp)
            final_text = resp.content if isinstance(resp.content, str) else str(resp.content)
            break

        resp = await llm_with_tools.ainvoke(messages)
        messages.append(resp)

        tool_calls = getattr(resp, "tool_calls", None) or []
        if not tool_calls:
            final_text = resp.content if isinstance(resp.content, str) else str(resp.content)
            break

        for tc in tool_calls:
            name = tc.get("name") if isinstance(tc, dict) else tc.name
            args = tc.get("args") if isinstance(tc, dict) else tc.args
            call_id = tc.get("id") if isinstance(tc, dict) else tc.id
            t = tool_map.get(name)
            if t is None:
                content = json.dumps({"error": f"unknown tool {name}"})
            else:
                try:
                    content = await t.ainvoke(args or {})
                except Exception as e:
                    content = json.dumps({"error": f"{type(e).__name__}: {e}"})
            messages.append(ToolMessage(content=content, tool_call_id=call_id))

    if not final_text:
        logger.warning("Brain ran out of iterations without final answer")
        return []

    # Parse final JSON
    parsed = _extract_json(final_text)
    raw_analyses = parsed.get("analyses", []) if isinstance(parsed, dict) else []

    analyses: list[dict] = []
    for a in raw_analyses:
        try:
            ar = AnalysisResult(
                symbol=str(a.get("symbol", "")).upper(),
                signal=str(a.get("signal", "HOLD")).upper(),
                strength=float(a.get("strength", 0.0) or 0.0),
                reasons=list(a.get("reasons", []) or []),
                indicators_summary="",
                llm_analysis=str(a.get("llm_analysis", "") or "")[:600],
                source=source,
            )
            analyses.append(ar.model_dump())
        except Exception as e:
            logger.warning(f"Skipping malformed analysis: {a} ({e})")

    logger.info(f"Brain produced {len(analyses)} analyses via {source}")

    # Persist each analysis so the brain can query its own history next cycle.
    for a in analyses:
        try:
            _memory.log_brain_decision({
                "symbol": a.get("symbol"),
                "signal": a.get("signal"),
                "strength": a.get("strength"),
                "reasons": a.get("reasons", []),
                "llm_analysis": a.get("llm_analysis", ""),
                "source": a.get("source", source),
            })
        except Exception:
            logger.exception("Failed to log brain decision")

    return analyses


def _extract_json(text: str) -> Any:
    """Find the first balanced {...} block in the LLM response, ignoring
    braces that appear inside JSON strings. Returns {} on any failure."""
    if not text:
        return {}
    # Strip markdown code fences if present
    t = text.strip()
    if t.startswith("```"):
        t = t.split("```", 2)[1] if "```" in t[3:] else t[3:]
        if t.startswith("json"):
            t = t[4:]
    start = t.find("{")
    if start < 0:
        return {}
    depth = 0
    in_str = False
    escape = False
    for i in range(start, len(t)):
        ch = t[i]
        if in_str:
            if escape:
                escape = False
            elif ch == "\\":
                escape = True
            elif ch == '"':
                in_str = False
            continue
        if ch == '"':
            in_str = True
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                try:
                    return json.loads(t[start:i+1])
                except Exception:
                    return {}
    return {}
