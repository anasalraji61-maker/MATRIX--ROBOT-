"""
Analysis Agent — produces a BUY/SELL/HOLD signal with conviction per symbol.

Combines:
  * Full indicator suite (RSI, Stoch, Williams %R, MACD, ADX, EMA stack, Ichimoku, BB, pivots, S/R, Fib)
  * Multi-timeframe consensus (M15/H1/H4/D1)
  * Volatility regime (low / normal / high)
  * Market sentiment (FinBERT / LLM-classified news)
  * LLM reasoning (Claude 3.5 / GPT-4o-mini via OpenRouter), with a richer prompt

Falls back to a feature-weighted ensemble score when no LLM key is available.
The ensemble is the cheap, deterministic stand-in for the future ML model
(Random Forest / LSTM) we will train on logged cycles.
"""
from __future__ import annotations

from config import get_settings
from models.schemas import AnalysisResult


async def run(state: dict) -> dict:
    settings = get_settings()
    from tools.universe_manager import is_full_power
    symbols = state.get("symbols_analyzed", settings.symbol_list)

    # FULL_POWER_DEMO — deterministic ensemble on all symbols (55), council decides after
    if is_full_power(settings) and getattr(settings, "full_analysis_all_symbols", True):
        return await _run_ensemble_all(state, symbols, settings)

    indicators_map = state.get("indicators", {})
    indicators_summaries = state.get("indicators_summaries", {})
    mtf_map = state.get("mtf", {})
    mtf_summaries = state.get("mtf_summaries", {})
    ict_map = state.get("ict", {})
    ict_summaries = state.get("ict_summaries", {})
    vol_map = state.get("volatility_regimes", {})
    sentiment = state.get("sentiment", {})

    analyses: list[dict] = []
    for symbol in symbols:
        ind = indicators_map.get(symbol, {})
        ind_summary = indicators_summaries.get(symbol, "No indicator data")
        mtf = mtf_map.get(symbol, {})
        mtf_summary = mtf_summaries.get(symbol, "")
        ict = ict_map.get(symbol, {})
        ict_summary = ict_summaries.get(symbol, "")
        vol = vol_map.get(symbol, {})

        if settings.has_llm:
            result = await _llm_analysis(symbol, ind, ind_summary, mtf, mtf_summary,
                                         ict, ict_summary, vol, sentiment, settings)
        else:
            result = _ensemble_analysis(symbol, ind, mtf, ict, vol, sentiment)

        analyses.append(result.model_dump())

    best = _pick_best_signal(analyses)
    return {**state, "analyses": analyses, "best_analysis": best}


async def _run_ensemble_all(state: dict, symbols: list, settings) -> dict:
    """Full universe ensemble — no per-symbol LLM (FULL_POWER_DEMO)."""
    indicators_map = state.get("indicators", {})
    mtf_map = state.get("mtf", {})
    ict_map = state.get("ict", {})
    vol_map = state.get("volatility_regimes", {})
    sentiment = state.get("sentiment", {})

    analyses: list[dict] = []
    for symbol in symbols:
        ind = indicators_map.get(symbol, {})
        result = _ensemble_analysis(
            symbol, ind, mtf_map.get(symbol, {}),
            ict_map.get(symbol, {}), vol_map.get(symbol, {}), sentiment,
        )
        analyses.append(result.model_dump())

    best = _pick_best_signal(analyses)
    return {**state, "analyses": analyses, "best_analysis": best}


# ── LLM path ──────────────────────────────────────────────────────────

async def _llm_analysis(
    symbol: str, ind: dict, ind_summary: str,
    mtf: dict, mtf_summary: str,
    ict: dict, ict_summary: str,
    vol: dict, sentiment: dict, settings,
) -> AnalysisResult:
    try:
        from langchain_openai import ChatOpenAI
        from langchain_core.messages import SystemMessage, HumanMessage

        from tools import llm_circuit
        if settings.effective_gemini_key:
            from langchain_google_genai import ChatGoogleGenerativeAI
            llm = ChatGoogleGenerativeAI(
                model=settings.gemini_model,
                google_api_key=settings.effective_gemini_key,
                temperature=0.1,
                max_output_tokens=500,
            )
            source = "gemini"
        elif settings.effective_openrouter_key and llm_circuit.is_openrouter_available():
            llm = ChatOpenAI(
                model="openai/gpt-4o-mini",
                openai_api_key=settings.effective_openrouter_key,
                openai_api_base="https://openrouter.ai/api/v1",
                temperature=0.1, max_tokens=500,
                max_retries=0,
            )
            source = "openrouter"
        elif settings.effective_openai_key:
            llm = ChatOpenAI(
                model="gpt-4o-mini",
                openai_api_key=settings.effective_openai_key,
                temperature=0.1, max_tokens=500,
            )
            source = "openai"
        else:
            return _ensemble_analysis(symbol, ind, mtf, ict, vol, sentiment)

        system = (
            "You are a senior quantitative forex analyst trained in ICT / SMC "
            "(Smart Money Concepts). Synthesise the FULL technical picture below "
            "(indicators, multi-timeframe trend consensus, ICT market-structure "
            "context — BOS/CHoCH/OB/FVG/liquidity/premium-discount/killzones, "
            "volatility regime, S/R/Fibonacci levels, macro sentiment) into ONE decision. "
            "Be conservative: only BUY/SELL when MTF consensus AND ICT bias agree with the "
            "primary indicator picture; otherwise HOLD. Prefer entries in discount zones "
            "with bullish CHoCH/OB confluence (or premium zones with bearish CHoCH/OB). "
            "Output strict JSON with keys: signal (BUY|SELL|HOLD), strength (0.0-1.0), "
            "reasons (list of 3-5 short strings), summary (1 sentence)."
        )

        ict_brief = (
            f"ICT: bias={ict.get('bias','neutral')} score={ict.get('score',0):+.2f} "
            f"structure={ict.get('structure','?')} event={ict.get('last_event','none')} "
            f"zone={ict.get('zone','equilibrium')} killzone={ict.get('active_killzone','none')} "
            f"confluence={ict.get('confluence_count',0)}"
        )

        human = (
            f"Symbol: {symbol}\n"
            f"Indicators: {ind_summary}\n"
            f"Multi-TF: {mtf_summary} (consensus={mtf.get('consensus','?')}, "
            f"score={mtf.get('score',0):+.2f}, aligned={mtf.get('aligned_count',0)}/4)\n"
            f"{ict_brief}\n"
            f"ICT one-liner: {ict_summary}\n"
            f"Volatility regime: {vol.get('regime','?')} "
            f"(percentile={vol.get('atr_percentile','?')}, size_mult={vol.get('size_multiplier',1.0)})\n"
            f"Levels: pivot={ind.get('pivot')} R1={ind.get('pivot_r1')} S1={ind.get('pivot_s1')} | "
            f"Fib 38.2={ind.get('fib_382')} 50={ind.get('fib_500')} 61.8={ind.get('fib_618')} | "
            f"swing S/R={ind.get('support')}/{ind.get('resistance')}\n"
            f"Sentiment: {sentiment.get('label','NEUTRAL')} (score={sentiment.get('score',0):.2f}, "
            f"confidence={sentiment.get('confidence',0):.2f})\n"
            "Output JSON now."
        )

        response = await llm.ainvoke([SystemMessage(content=system), HumanMessage(content=human)])
        import json, re
        m = re.search(r"\{.*\}", response.content, re.DOTALL)
        if m:
            data = json.loads(m.group())
            return AnalysisResult(
                symbol=symbol,
                signal=data.get("signal", "HOLD").upper(),
                strength=float(data.get("strength", 0.5)),
                reasons=data.get("reasons", ["LLM analysis"])[:5],
                indicators_summary=ind_summary,
                llm_analysis=data.get("summary"),
                source=source,
            )
    except Exception as e:
        try:
            from tools import llm_circuit
            if llm_circuit.is_credit_or_auth_error(e):
                llm_circuit.trip_openrouter(f"analysis_agent: {e}")
        except Exception:
            pass

    return _ensemble_analysis(symbol, ind, mtf, ict, vol, sentiment)


# ── Ensemble / rule-based path (also serves as ML stand-in) ───────────

# Feature weights — tuned by hand; future ML will replace this with learned coefficients
_W = {
    "rsi": 1.5, "stoch": 1.0, "williams": 0.8, "macd": 1.5,
    "ema_stack": 2.0, "ema200": 1.0, "adx": 1.5, "ichimoku": 1.2,
    "mtf": 3.0,                 # multi-TF consensus
    "ict": 3.5,                 # heaviest — ICT/SMC structural bias
    "sentiment": 1.0,
    "near_support": 1.2, "near_resistance": 1.2,
}


def _ensemble_analysis(symbol: str, ind: dict, mtf: dict, ict: dict, vol: dict, sentiment: dict) -> AnalysisResult:
    score = 0.0
    reasons: list[str] = []

    rsi = ind.get("rsi_14")
    if rsi is not None:
        if rsi < 35:
            score += _W["rsi"]; reasons.append(f"RSI {rsi:.1f} oversold (+buy)")
        elif rsi > 65:
            score -= _W["rsi"]; reasons.append(f"RSI {rsi:.1f} overbought (+sell)")

    stoch_k = ind.get("stoch_k")
    if stoch_k is not None:
        if stoch_k < 20:
            score += _W["stoch"]; reasons.append(f"Stoch %K {stoch_k:.1f} oversold")
        elif stoch_k > 80:
            score -= _W["stoch"]; reasons.append(f"Stoch %K {stoch_k:.1f} overbought")

    wr = ind.get("williams_r")
    if wr is not None:
        if wr < -80:
            score += _W["williams"]; reasons.append(f"Williams %R {wr:.1f} oversold")
        elif wr > -20:
            score -= _W["williams"]; reasons.append(f"Williams %R {wr:.1f} overbought")

    mh = ind.get("macd_hist")
    if mh is not None:
        if mh > 0:
            score += _W["macd"]; reasons.append(f"MACD hist {mh:.5f} bullish momentum")
        else:
            score -= _W["macd"]; reasons.append(f"MACD hist {mh:.5f} bearish momentum")

    ema20, ema50, ema200 = ind.get("ema_20"), ind.get("ema_50"), ind.get("ema_200")
    if ema20 and ema50:
        if ema20 > ema50:
            score += _W["ema_stack"]; reasons.append("EMA20 > EMA50 bullish")
        elif ema20 < ema50:
            score -= _W["ema_stack"]; reasons.append("EMA20 < EMA50 bearish")
    if ema200 and ind.get("bb_mid"):
        # use bb_mid as a price proxy if explicit price not present
        close_proxy = ind.get("bb_mid")
        if close_proxy and close_proxy > ema200:
            score += _W["ema200"]; reasons.append("Price > EMA200 (LT bullish)")
        elif close_proxy and close_proxy < ema200:
            score -= _W["ema200"]; reasons.append("Price < EMA200 (LT bearish)")

    adx = ind.get("adx_14")
    di_p, di_m = ind.get("di_plus"), ind.get("di_minus")
    if adx is not None and adx >= 25 and di_p is not None and di_m is not None:
        if di_p > di_m:
            score += _W["adx"]; reasons.append(f"ADX {adx:.0f} strong, DI+>DI-")
        else:
            score -= _W["adx"]; reasons.append(f"ADX {adx:.0f} strong, DI->DI+")

    ich = ind.get("ichimoku_above_cloud")
    if ich is True:
        score += _W["ichimoku"]; reasons.append("Above Ichimoku cloud")
    elif ich is False:
        score -= _W["ichimoku"]; reasons.append("Below Ichimoku cloud")

    # MTF
    mtf_score = float(mtf.get("score", 0.0) or 0.0)
    if abs(mtf_score) >= 0.25:
        score += _W["mtf"] * mtf_score
        cons = (mtf.get("consensus") or "neutral").upper()
        reasons.append(f"MTF {cons} ({mtf.get('aligned_count',0)}/4 aligned, score={mtf_score:+.2f})")

    # ICT / SMC — heaviest structural weight (configurable)
    ict_score = float((ict or {}).get("score", 0.0) or 0.0)
    ict_weight = float(get_settings().ict_ensemble_weight)
    if abs(ict_score) >= 0.20:
        score += ict_weight * ict_score
        evt = (ict or {}).get("last_event", "none")
        zone = (ict or {}).get("zone", "equilibrium")
        kz = (ict or {}).get("active_killzone", "none")
        reasons.append(
            f"ICT {(ict or {}).get('bias','neutral').upper()} "
            f"(evt={evt}, zone={zone}, kz={kz}, score={ict_score:+.2f})"
        )

    # Sentiment
    s_lab = (sentiment.get("label") or "NEUTRAL").upper()
    s_sc = sentiment.get("score", 0.0) or 0.0
    if s_lab == "POSITIVE" and s_sc > 0.2:
        score += _W["sentiment"]; reasons.append(f"News sentiment +{s_sc:.2f}")
    elif s_lab == "NEGATIVE" and s_sc < -0.2:
        score -= _W["sentiment"]; reasons.append(f"News sentiment {s_sc:.2f}")

    # S/R proximity (within ATR of swing low/high)
    atr = ind.get("atr_14") or 0
    support = ind.get("support"); resistance = ind.get("resistance")
    last_price = ind.get("bb_mid")
    if last_price and atr and support and resistance:
        if abs(last_price - support) <= atr * 2:
            score += _W["near_support"]; reasons.append(f"Near support {support}")
        if abs(last_price - resistance) <= atr * 2:
            score -= _W["near_resistance"]; reasons.append(f"Near resistance {resistance}")

    # Volatility regime adjusts conviction (high vol → less confident)
    vol_mult = float(vol.get("size_multiplier", 1.0) or 1.0)
    # Score → signal + strength (normalize over max possible)
    max_score = sum(_W.values())
    norm = max(-1.0, min(1.0, score / max_score))
    if norm >= 0.25:
        signal = "BUY"
        strength = round(min(0.5 + abs(norm) * 0.7, 0.97) * (0.85 + 0.15 * vol_mult), 3)
    elif norm <= -0.25:
        signal = "SELL"
        strength = round(min(0.5 + abs(norm) * 0.7, 0.97) * (0.85 + 0.15 * vol_mult), 3)
    else:
        signal = "HOLD"; strength = 0.3

    if not reasons:
        reasons = ["Insufficient indicator data — holding"]

    return AnalysisResult(
        symbol=symbol,
        signal=signal,
        strength=strength,
        reasons=reasons[:5],
        indicators_summary=f"Score={score:+.2f}/{max_score:.1f} norm={norm:+.2f} vol_mult={vol_mult}",
        source="ensemble",
    )


def _pick_best_signal(analyses: list[dict]) -> dict:
    actionable = [a for a in analyses if a["signal"] != "HOLD"]
    if not actionable:
        return analyses[0] if analyses else {}
    return max(actionable, key=lambda a: a["strength"])
