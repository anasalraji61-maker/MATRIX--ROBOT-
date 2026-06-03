"""
Sentiment Agent — classifies news articles using FinBERT (HuggingFace Inference API).
Falls back to keyword-based scoring when HUGGINGFACE_API_KEY is not set.
"""
import httpx
import re
from config import get_settings
from models.schemas import SentimentResult

FINBERT_MODEL = "ProsusAI/finbert"
HF_BASE = "https://api-inference.huggingface.co/models"

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
    news_items = state.get("market_data", {}).get("news", [])

    if not news_items:
        result = SentimentResult(score=0.0, label="NEUTRAL",
                                 confidence=0.5, news_count=0, source="mock")
        return {**state, "sentiment": result.model_dump()}

    texts = [f"{n['title']}. {n['summary']}" for n in news_items[:8]]

    if settings.huggingface_api_key:
        result = await _finbert_classify(texts, settings.huggingface_api_key)
    else:
        result = _keyword_classify(texts)

    return {**state, "sentiment": result.model_dump()}


async def _finbert_classify(texts: list[str], api_key: str) -> SentimentResult:
    headers = {"Authorization": f"Bearer {api_key}"}
    scores = {"positive": 0.0, "negative": 0.0, "neutral": 0.0}
    count = 0

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

    if count == 0:
        return _keyword_classify(texts)

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
