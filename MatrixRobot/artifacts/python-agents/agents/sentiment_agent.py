"""
Sentiment Agent — classifies news for the trading cycle.

Pipeline:
  1. FinBERT via HuggingFace (free) — fast score
  2. GPT-4o-mini briefing via OpenRouter — market impact summary (Phase A)
  3. pgvector search — similar past news/briefings (when Postgres enabled)
  4. Fallback: GPT classify if FinBERT fails, then keyword scoring
"""
from __future__ import annotations

import json
import logging
import re

import httpx

from config import get_settings
from models.schemas import SentimentResult

logger = logging.getLogger("matrix.sentiment")

FINBERT_MODEL = "ProsusAI/finbert"
HF_BASE = "https://api-inference.huggingface.co/models"
OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"

POSITIVE_WORDS = {
    "surge", "gain", "rally", "rise", "boost", "strong", "bullish",
    "optimism", "growth", "recovery", "beat", "exceed", "up", "higher",
}
NEGATIVE_WORDS = {
    "fall", "drop", "decline", "plunge", "weak", "bearish", "risk",
    "concern", "fear", "sell", "crash", "slump", "miss", "down", "lower",
}


async def run(state: dict) -> dict:
    settings = get_settings()
    market = state.get("market_data", {})
    news_items = market.get("news", [])
    news_source = market.get("news_source", "unknown")

    if not news_items:
        result = SentimentResult(
            score=0.0, label="NEUTRAL", confidence=0.5,
            news_count=0, source="no_news",
        )
        out = result.model_dump()
        out["briefing"] = "No headlines available this cycle."
        out["similar_context"] = ""
        return {**state, "sentiment": out}

    texts = [f"{n['title']}. {n.get('summary', '')}" for n in news_items[:8]]
    headlines_block = "\n".join(f"- {t[:200]}" for t in texts)
    light_cycle = (state.get("cycle_plan") or {}).get("cycle_type") in ("scanner", "maintenance")

    result: SentimentResult | None = None
    if not light_cycle and settings.huggingface_api_key:
        result = await _finbert_classify(texts, settings.huggingface_api_key)
    if result is None and not light_cycle and settings.effective_openrouter_key:
        result = await _openrouter_classify(texts, settings.effective_openrouter_key)
    if result is None:
        result = _keyword_classify(texts)

    out = result.model_dump()
    out["news_feed_source"] = news_source
    out["finbert_label"] = out.get("label")
    out["finbert_score"] = out.get("score")

    # Phase A — GPT market briefing (skip in scanner/maintenance cycles to save cost)
    briefing = ""
    if settings.effective_openrouter_key and not light_cycle:
        briefing = await _gpt_briefing(
            headlines_block, out, settings.effective_openrouter_key,
        ) or ""
    out["briefing"] = briefing

    # pgvector — store + retrieve similar context
    similar_context = ""
    try:
        from tools import semantic_memory
        if briefing:
            query = f"{out.get('label')} {briefing}"
            matches = await semantic_memory.search_similar(query, kind="briefing", limit=3)
            similar_context = semantic_memory.format_similar_context(matches)
            await semantic_memory.store(
                "briefing",
                f"Sentiment {out.get('label')} ({out.get('score'):+.2f}). {briefing}",
                metadata={"news_source": news_source, "news_count": len(texts)},
            )
    except Exception as e:
        logger.warning("Semantic memory skipped: %s", e)
    out["similar_context"] = similar_context

    return {**state, "sentiment": out}


async def _gpt_briefing(headlines: str, sentiment: dict, api_key: str) -> str | None:
    prompt = (
        "You are a forex/metals market analyst. Write a concise briefing (4-6 lines) for a "
        "trading desk. Cover: overall mood, top 2 headlines, likely USD/EUR/Gold impact, "
        "and one risk to watch. No markdown.\n\n"
        f"FinBERT sentiment: {sentiment.get('label')} score={sentiment.get('score'):+.2f} "
        f"confidence={sentiment.get('confidence', 0):.2f}\n\n"
        f"Headlines:\n{headlines}"
    )
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            r = await client.post(
                OPENROUTER_URL,
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                    "HTTP-Referer": "https://matrix-robot.local",
                    "X-Title": "Matrix Robot Briefing",
                },
                json={
                    "model": "openai/gpt-4o-mini",
                    "messages": [{"role": "user", "content": prompt}],
                    "temperature": 0.2,
                    "max_tokens": 280,
                },
            )
        if r.status_code != 200:
            logger.warning("GPT briefing HTTP %s", r.status_code)
            return None
        content = r.json()["choices"][0]["message"]["content"]
        return (content or "").strip()[:1200]
    except Exception as e:
        logger.warning("GPT briefing failed: %s", e)
        return None


async def _finbert_classify(texts: list[str], api_key: str) -> SentimentResult | None:
    headers = {"Authorization": f"Bearer {api_key}"}
    scores = {"positive": 0.0, "negative": 0.0, "neutral": 0.0}
    count = 0

    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            for text in texts:
                try:
                    r = await client.post(
                        f"{HF_BASE}/{FINBERT_MODEL}",
                        headers=headers,
                        json={"inputs": text[:512]},
                    )
                    if r.status_code == 200:
                        predictions = r.json()
                        if isinstance(predictions, list) and predictions:
                            for item in predictions[0]:
                                label = item["label"].lower()
                                if label in scores:
                                    scores[label] += item["score"]
                            count += 1
                except Exception:
                    continue
    except Exception as e:
        logger.warning("FinBERT unavailable: %s", e)
        return None

    if count == 0:
        return None

    for k in scores:
        scores[k] /= count

    top_label = max(scores, key=scores.__getitem__)
    net_score = scores["positive"] - scores["negative"]

    return SentimentResult(
        score=round(net_score, 4),
        label=top_label.upper(),
        confidence=round(scores[top_label], 4),
        news_count=len(texts),
        source="finbert",
    )


async def _openrouter_classify(texts: list[str], api_key: str) -> SentimentResult | None:
    headlines = "\n".join(f"- {t[:200]}" for t in texts)
    prompt = (
        "Classify overall market sentiment from these headlines for forex/metals trading.\n"
        "Reply with JSON only: "
        '{"label":"POSITIVE"|"NEGATIVE"|"NEUTRAL","score":-1.0 to 1.0,"confidence":0.0 to 1.0}\n\n'
        f"Headlines:\n{headlines}"
    )
    try:
        async with httpx.AsyncClient(timeout=25.0) as client:
            r = await client.post(
                OPENROUTER_URL,
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                    "HTTP-Referer": "https://matrix-robot.local",
                    "X-Title": "Matrix Robot Sentiment",
                },
                json={
                    "model": "openai/gpt-4o-mini",
                    "messages": [{"role": "user", "content": prompt}],
                    "temperature": 0.0,
                    "max_tokens": 120,
                },
            )
        if r.status_code != 200:
            logger.warning("OpenRouter sentiment HTTP %s", r.status_code)
            return None
        content = r.json()["choices"][0]["message"]["content"]
        match = re.search(r"\{[^{}]+\}", content)
        if not match:
            return None
        data = json.loads(match.group())
        label = str(data.get("label", "NEUTRAL")).upper()
        if label not in ("POSITIVE", "NEGATIVE", "NEUTRAL"):
            label = "NEUTRAL"
        score = float(data.get("score", 0.0))
        score = max(-1.0, min(1.0, score))
        confidence = float(data.get("confidence", 0.7))
        confidence = max(0.0, min(1.0, confidence))
        return SentimentResult(
            score=round(score, 4),
            label=label,
            confidence=round(confidence, 4),
            news_count=len(texts),
            source="openrouter",
        )
    except Exception as e:
        logger.warning("OpenRouter sentiment failed: %s", e)
        return None


def _keyword_classify(texts: list[str]) -> SentimentResult:
    pos = neg = 0
    for text in texts:
        words = set(re.findall(r"\b\w+\b", text.lower()))
        pos += len(words & POSITIVE_WORDS)
        neg += len(words & NEGATIVE_WORDS)

    total = pos + neg or 1
    score = (pos - neg) / total
    label = "POSITIVE" if score > 0.1 else "NEGATIVE" if score < -0.1 else "NEUTRAL"
    confidence = abs(score) * 0.6 + 0.4

    return SentimentResult(
        score=round(score, 4),
        label=label,
        confidence=round(min(confidence, 1.0), 4),
        news_count=len(texts),
        source="keyword",
    )
