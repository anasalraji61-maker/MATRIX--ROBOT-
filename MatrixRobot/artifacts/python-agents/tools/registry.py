"""
Tool registry for the Agentic Brain.

Wraps every analytical capability the LLM can call. Each tool is a thin
LangChain @tool function bound to the CURRENT cycle's state, so it sees
the same data the rest of the pipeline already fetched.

Two design rules:
  • Tools are read-only. They never mutate state or open trades. The brain's
    final decision is recorded via `propose_trade`, which returns a dict the
    brain then echoes in its summary — the actual execution is gated by
    risk_agent + execution_agent downstream.
  • Tools return COMPACT JSON strings (LLM-friendly). No raw bar arrays.
"""
from __future__ import annotations
import json
from typing import Any

from langchain_core.tools import tool

from tools.strategies import (
    wyckoff as _wyckoff,
    elliott as _elliott,
    harmonic as _harmonic,
    volume_profile as _vp,
    chart_patterns as _cp,
)
from tools import memory as _memory
from tools import sandbox as _sandbox
from tools import adaptive_policy as _ape


def _j(obj: Any) -> str:
    """Compact JSON for LLM consumption. Floats trimmed to 5 dp."""
    def default(o):
        if isinstance(o, float):
            return round(o, 5)
        return str(o)
    try:
        return json.dumps(obj, default=default, separators=(",", ":"))[:2000]
    except Exception:
        return json.dumps({"error": "serialize_failed"})


def build_tools(state: dict):
    """Return a list of LangChain @tool callables bound to this state."""
    bars_cache: dict[str, list[dict]] = state.get("_bars_h1", {})

    def _bars(sym: str) -> list[dict]:
        return bars_cache.get(sym) or []

    @tool
    def get_indicators(symbol: str) -> str:
        """Full technical indicators for a symbol: RSI, MACD, Stoch, ADX,
        EMAs (20/50/200), Bollinger Bands, ATR, Ichimoku, pivots, S/R, Fib.
        Use this FIRST to get the broad technical picture."""
        return _j((state.get("indicators") or {}).get(symbol.upper(), {}))

    @tool
    def get_mtf_consensus(symbol: str) -> str:
        """Multi-timeframe trend consensus across M15/H1/H4/D1.
        Returns aligned_count and consensus label. Use to confirm a trade
        direction has alignment across timeframes (≥3 of 4 is strong)."""
        return _j((state.get("mtf") or {}).get(symbol.upper(), {}))

    @tool
    def get_ict_smc(symbol: str) -> str:
        """ICT / Smart Money Concepts analysis: BOS, CHoCH, order blocks,
        FVGs, liquidity pools, premium/discount zone, killzone status.
        Use when you suspect institutional accumulation / distribution."""
        return _j((state.get("ict") or {}).get(symbol.upper(), {}))

    @tool
    def get_wyckoff(symbol: str) -> str:
        """Wyckoff phase: ACCUMULATION / MARKUP / DISTRIBUTION / MARKDOWN.
        Detects springs (false breakdowns) and upthrusts (false breakouts).
        Use to gauge whether smart money is loading up or unloading."""
        return _j(_wyckoff.analyze(_bars(symbol.upper()), symbol.upper()))

    @tool
    def get_elliott_wave(symbol: str) -> str:
        """Elliott Wave count: current wave (1-5 impulse or A-C correction)
        plus expected next leg. Use to time entries with wave 3 (strongest)
        or wave 4 pullback entries before wave 5."""
        return _j(_elliott.analyze(_bars(symbol.upper()), symbol.upper()))

    @tool
    def get_harmonic_pattern(symbol: str) -> str:
        """Harmonic pattern detector: Gartley, Bat, Butterfly, Crab, Cypher,
        Shark. Returns pattern name + PRZ (potential reversal zone).
        Use for high-precision reversal entries at completed D points."""
        return _j(_harmonic.analyze(_bars(symbol.upper()), symbol.upper()))

    @tool
    def get_volume_profile(symbol: str) -> str:
        """Volume Profile: POC (point of control), VAH/VAL (value area
        high/low), HVN/LVN (high/low volume nodes). Use to identify
        magnet prices and acceptance/rejection levels."""
        return _j(_vp.analyze(_bars(symbol.upper()), symbol.upper()))

    @tool
    def get_chart_pattern(symbol: str) -> str:
        """Classic chart patterns: double top/bottom, head & shoulders,
        triangles (asc/desc/sym), wedges. Returns the strongest match.
        Use for confirmation alongside other tools."""
        return _j(_cp.analyze(_bars(symbol.upper()), symbol.upper()))

    @tool
    def get_volatility_regime(symbol: str) -> str:
        """ATR percentile classification: low / normal / high vol.
        Includes recommended position-size multiplier. Use to know whether
        the market is asleep or wild."""
        return _j((state.get("volatility_regimes") or {}).get(symbol.upper(), {}))

    @tool
    def get_market_sentiment() -> str:
        """LLM-classified news sentiment (BULLISH/BEARISH/NEUTRAL) across
        the universe with per-article scores. Use to gauge the news backdrop."""
        return _j(state.get("sentiment") or {})

    @tool
    def get_economic_calendar() -> str:
        """Upcoming HIGH-impact events + current blackout status. Use to
        avoid opening trades right before NFP / FOMC / ECB."""
        return _j(state.get("economic_calendar") or {})

    @tool
    def get_correlation_report() -> str:
        """Current correlation exposure groups + which symbols/directions
        are blocked due to stacking. Use to avoid duplicating risk."""
        return _j(state.get("correlation_report") or {})

    @tool
    def get_prop_status() -> str:
        """FundedNext compliance snapshot: daily/total DD, margin used,
        open risk, can_trade flag, block_reason. ALWAYS check this BEFORE
        proposing a trade — if can_trade=false you must HOLD."""
        return _j(state.get("prop_status") or {})

    @tool
    def get_quote(symbol: str) -> str:
        """Current bid/ask/mid + 24h change for a symbol."""
        quotes = (state.get("market_data") or {}).get("quotes", [])
        for q in quotes:
            if q.get("symbol") == symbol.upper():
                return _j(q)
        return _j({"error": "symbol_not_found", "symbol": symbol})

    @tool
    def universe_snapshot() -> str:
        """One-line summary per symbol — trend, MTF consensus, ICT bias,
        vol regime. Use FIRST to scan all symbols and pick the 1-3 worth
        deep analysis. Saves tool calls."""
        out = {}
        ind_map = state.get("indicators") or {}
        mtf_map = state.get("mtf") or {}
        ict_map = state.get("ict") or {}
        vol_map = state.get("volatility_regimes") or {}
        for sym in state.get("symbols_analyzed", []):
            ind = ind_map.get(sym, {})
            mtf = mtf_map.get(sym, {})
            ict = ict_map.get(sym, {})
            vol = vol_map.get(sym, {})
            out[sym] = {
                "trend": ind.get("trend"),
                "momentum": ind.get("momentum"),
                "rsi": ind.get("rsi_14"),
                "mtf": mtf.get("consensus"),
                "ict_bias": ict.get("bias"),
                "vol": vol.get("regime"),
            }
        return _j(out)

    @tool
    def query_history(symbol: str = "", limit: int = 5) -> str:
        """Return your own recent analyses (and any closed trade outcomes) for
        a symbol — or across the whole universe if symbol is empty. Use this to:
          • avoid flip-flopping (don't BUY a symbol you just SELL'd 30 min ago)
          • see whether past BUYs on this symbol made or lost money
          • detect patterns in your own behaviour (always wrong on USDJPY mornings?)
        Returns: {decisions: [{ts,signal,strength,reasons,llm_analysis}],
                  outcomes:  [{ts,symbol,side,entry,exit,pnl,reason}]}."""
        try:
            lim = max(1, min(int(limit or 5), 20))
        except Exception:
            lim = 5
        sym = (symbol or "").strip().upper() or None
        return _j({
            "decisions": _memory.get_recent_decisions(sym, lim),
            "outcomes":  _memory.get_recent_outcomes(sym, lim),
        })

    @tool
    def get_adaptive_policy() -> str:
        """Return the current Adaptive Policy Envelope (APE) state.

        Shows:
          • risk_multiplier        — current position-size multiplier (0.3–1.0; 1.0=baseline)
          • paused_symbols         — symbols you previously paused (still active)
          • conviction_override    — tightened entry threshold if set
          • conviction_expires_at  — when conviction_override auto-expires
          • skip_session_active    — whether a SKIP_SESSION is currently in effect
          • skip_session_until     — timestamp when skip window ends
          • consecutive_losses     — loss streak counter (auto-tracked by execution layer)
          • ape_changes_last_24h   — number of APE changes used in last 24h
          • ape_changes_remaining_24h — how many more changes you can make today
          • adaptation_log         — your last 20 autonomous adaptations with reasons
          • allowed_adaptations    — what you CAN change autonomously
          • forbidden_adaptations  — what requires human approval (env/secrets)
          • valid_symbols          — symbols accepted by PAUSE_SYMBOL / RESUME_SYMBOL

        Call this at the START of every cycle — before universe_snapshot — so you
        know the current policy context and don't miss an active pause or risk cut."""
        return _j(_ape.get_snapshot())

    @tool
    def apply_adaptive_change(
        adaptation_type: str,
        reason: str,
        expected_benefit: str,
        rollback_condition: str,
        value: str = "",
        expires_hours: int = 12,
        trigger_summary: str = "",
        current_daily_dd_pct: float = 0.0,
    ) -> str:
        """Apply a defensive, FundedNext-compliant adaptation autonomously.

        ALLOWED adaptation_type values (defensive only — no human approval needed):
          REDUCE_RISK       — shrink position sizes; value=multiplier (e.g. "0.5" = half size).
                             Min 0.3, max stays at 1.0. Cannot raise risk.
          RESET_RISK        — restore risk to baseline (1.0) ONLY when safe:
                             requires 2h cooldown + 0 consecutive losses + daily DD < 3%.
                             Pass current_daily_dd_pct so the guard can verify.
          PAUSE_SYMBOL      — stop trading a symbol; value=SYMBOL (e.g. "EURUSD").
                             Expires automatically after expires_hours (max 24).
                             Only symbols in valid_symbols list are accepted.
          RESUME_SYMBOL     — un-pause a symbol; value=SYMBOL.
                             Blocked if symbol was paused less than 1h ago.
          TIGHTEN_CONVICTION — raise entry bar; value=threshold (e.g. "0.75").
                             Range 0.55–0.85. Auto-expires after expires_hours (max 24h).
          RESET_CONVICTION  — restore conviction threshold to default.
          SKIP_SESSION      — skip current cycle (no trades). Uses a time window so all
                             symbols in the cycle are skipped, not just the first one.
                             Default window: 2h. Max: 3h.

        FORBIDDEN (will be rejected — requires human action):
          INCREASE_RISK, ENABLE_LIVE, CHANGE_DRAWDOWN_LIMITS, USE_HFT,
          USE_MARTINGALE, USE_GRID, COPY_TRADING, CHANGE_CORE_STRATEGY

        Anti-flapping limits (enforced server-side):
          • Max 3 APE changes per 24h (check ape_changes_remaining_24h in get_adaptive_policy)
          • Min 30 min between the same adaptation type
          • RESET_* types are exempt from rate limiting

        Every call is logged with your reason, trigger data, expected benefit,
        rollback condition, and FundedNext compliance note.

        Parameters:
          adaptation_type      : one of the ALLOWED types above
          reason               : why you are making this change (cite specific data)
          expected_benefit     : what you expect this to improve
          rollback_condition   : when you will RESET this adaptation (be specific)
          value                : required for REDUCE_RISK, PAUSE_SYMBOL, RESUME_SYMBOL,
                                TIGHTEN_CONVICTION (pass as string, e.g. "0.5" or "EURUSD")
          expires_hours        : how many hours until auto-expiry (default 12, max 24)
          trigger_summary      : brief summary of the data that triggered this decision
          current_daily_dd_pct : pass current daily drawdown % when calling RESET_RISK
                                (get from get_prop_status → daily_loss_pct)
        """
        trigger_data = {"trigger_summary": trigger_summary} if trigger_summary else {}
        parsed_value: float | str | None = None
        if value:
            try:
                parsed_value = float(value)
            except (ValueError, TypeError):
                parsed_value = value
        return _j(_ape.apply_adaptation(
            adaptation_type=adaptation_type,
            reason=reason,
            trigger_data=trigger_data,
            expected_benefit=expected_benefit,
            rollback_condition=rollback_condition,
            value=parsed_value,
            expires_hours=expires_hours,
            daily_dd_pct=float(current_daily_dd_pct or 0.0),
        ))

    @tool
    def run_python_code(code: str) -> str:
        """Run a short Python snippet against the bars the data agent already
        fetched. Available globals: `bars` (dict[symbol] -> list[{open,high,low,close,volume,ts}]),
        `get_bars(symbol)`, `np` (numpy), `pd` (pandas), `math`, `statistics`, `json`.
        ASSIGN your answer to a variable named `result` — that's what gets returned.
        IMPORTS ARE BLOCKED. Use the pre-injected `np`, `pd`, `math`, `statistics`
        modules directly — do NOT write `import numpy as np`. 5-second wall-clock limit.
        No file or network access.

        AVAILABILITY: Only enabled in PAPER_MODE. Automatically disabled in ACTIVE
        trading mode as a security measure. Do not attempt to use it in ACTIVE mode.

        Use this when no pre-built tool covers what you want to compute —
        e.g. a custom rolling z-score, a bespoke divergence detector, a
        correlation between two custom features, a regression line slope, etc.

        Example (correct — uses pre-injected np):
          code = "c = [b['close'] for b in get_bars('EURUSD')]\\nresult = float(np.std(c[-50:]) / np.mean(c[-50:]))"
        """
        from config import get_settings as _gs
        _settings = _gs()
        if getattr(_settings, "trading_state", "PAPER_MODE") == "ACTIVE":
            return _j({
                "error": (
                    "run_python_code is DISABLED in ACTIVE trading mode. "
                    "This tool is only available in PAPER_MODE. "
                    "Use the pre-built analytical tools instead."
                ),
                "mode": "ACTIVE",
            })
        return _j(_sandbox.run(code or "", bars_cache))

    return [
        get_adaptive_policy,
        universe_snapshot,
        get_indicators,
        get_mtf_consensus,
        get_ict_smc,
        get_wyckoff,
        get_elliott_wave,
        get_harmonic_pattern,
        get_volume_profile,
        get_chart_pattern,
        get_volatility_regime,
        get_market_sentiment,
        get_economic_calendar,
        get_correlation_report,
        get_prop_status,
        get_quote,
        query_history,
        apply_adaptive_change,
        run_python_code,
    ]
