import re

MODEL_VERSION = "local-lexicon-1.0"
POSITIVE = {
    "amazing", "awesome", "best", "brilliant", "easy", "excellent", "fantastic",
    "fast", "friendly", "good", "great", "happy", "helpful", "love", "perfect",
    "quick", "recommend", "reliable", "smooth", "thank", "wonderful",
}
NEGATIVE = {
    "angry", "bad", "broken", "complaint", "delay", "disappointed", "expensive",
    "hate", "late", "poor", "problem", "refund", "slow", "terrible", "unhelpful",
    "unreliable", "waste", "worst",
}
NEGATORS = {"not", "never", "no", "hardly"}


def predict(text: str) -> dict[str, object]:
    tokens = re.findall(r"[a-z']+", text.casefold())
    if len(tokens) < 2:
        return {"sentiment": "uncertain", "confidence": 0.0, "uncertain": True}
    score = 0
    for index, token in enumerate(tokens):
        direction = 1 if token in POSITIVE else -1 if token in NEGATIVE else 0
        if direction and any(word in NEGATORS for word in tokens[max(0, index - 3):index]):
            direction *= -1
        score += direction
    if score == 0:
        return {"sentiment": "neutral", "confidence": 0.5, "uncertain": False}
    confidence = min(0.95, 0.55 + abs(score) * 0.08)
    if abs(score) == 1 and len(tokens) < 5:
        return {"sentiment": "uncertain", "confidence": confidence, "uncertain": True}
    return {
        "sentiment": "positive" if score > 0 else "negative",
        "confidence": confidence,
        "uncertain": confidence < 0.65,
    }
