from __future__ import annotations

import re
import time

from app.nlu.entities import extract_rule_entities
from app.nlu.types import NLUResult
from shared.labels import INTENTS

# Phrase lists are intentionally compact but bilingual. The trained transformer
# replaces this fallback once an artifact is present; these rules keep local
# development and the test suite deterministic.
KEYWORDS: dict[str, list[str]] = {
    "greeting": [
        "hello", "hi", "hey", "hii", "namaste", "namaskar", "good morning",
        "good afternoon", "good evening", "howdy", "start", "are you there",
        "kya haal", "kaise ho", "salaam",
    ],
    "order_status": [
        "where is my order", "order status", "track my order", "tracking",
        "track order", "when will it arrive", "when will my order arrive",
        "has it shipped", "shipped yet", "out for delivery", "delivery status",
        "mera order kahan", "order kahan hai", "order kab aayega", "kab milega",
        "tracking number", "delivery update", "order update", "late delivery",
    ],
    "return_refund": [
        "return", "refund", "exchange", "money back", "send it back",
        "return policy", "refund policy", "cancel my order", "cancel order",
        "want a refund", "return my order", "replace", "damaged refund",
        "wapas", "paisa wapas", "refund chahiye", "return karna", "exchange karna",
    ],
    "product_info": [
        "tell me about", "details of", "features", "specification", "specs",
        "dimensions", "size", "colour", "color", "material", "made of",
        "fabric", "weight", "care instructions", "what is included",
        "in stock", "availability", "how does it work", "product info",
        "kaun sa material", "kya material", "kaise use", "size kya",
        "kitne inch", "kaunsa colour",
    ],
    "pricing": [
        "price", "pricing", "cost", "how much", "how much does", "rate",
        "discount", "offer", "sale", "coupon", "promo code", "cheapest",
        "best price", "kitna", "kitne ka", "kimat", "daam", "sasta",
        "discount milega", "price kya",
    ],
    "complaint": [
        "complaint", "damaged", "broken", "defective", "wrong item",
        "not working", "doesn't work", "poor quality", "bad quality",
        "terrible", "worst", "awful", "unacceptable", "disappointed",
        "late again", "missing item", "missing part", "scratched",
        "kharab", "toota", "galat item", "bakwas", "ghatiya", "bekar",
        "shikayat", "problem hai",
    ],
    "human_agent": [
        "human", "real person", "agent", "representative", "someone",
        "customer service", "customer care", "support team", "talk to a person",
        "speak to a human", "connect me", "manager", "supervisor",
        "insaan", "aadmi se baat", "agent se baat", "customer care se",
        "baat karwao",
    ],
    "goodbye": [
        "bye", "goodbye", "see you", "thanks", "thank you", "that's all",
        "that is all", "no more questions", "have a good day", "done",
        "shukriya", "dhanyavad", "theek hai", "chalta hoon", "phir milte",
    ],
    "other": [
        "weather", "joke", "who are you", "what are you", "your name",
        "politics", "news", "stock market", "cricket score", "write code",
    ],
}


def _phrase_present(text: str, phrase: str) -> bool:
    if " " in phrase:
        return phrase in text
    return re.search(rf"(?<!\w){re.escape(phrase)}(?!\w)", text) is not None


def classify_text(text: str) -> tuple[str, float, list[dict]]:
    normalized = text.lower().strip()
    scores = {intent: 0.0 for intent in INTENTS}
    hits: dict[str, list[str]] = {intent: [] for intent in INTENTS}

    for intent, phrases in KEYWORDS.items():
        for phrase in phrases:
            if _phrase_present(normalized, phrase):
                scores[intent] += 0.65 + 0.2 * len(phrase.split())
                hits[intent].append(phrase)

    ranked = sorted(scores.items(), key=lambda item: item[1], reverse=True)
    best_intent, best_score = ranked[0]
    second_score = ranked[1][1]

    if best_score <= 0:
        return "other", 0.30, [{"intent": "other", "confidence": 0.30}]

    # The rules use a margin-based confidence so an unambiguous phrase clears
    # the handoff threshold, while mixed-signal utterances stay uncertain.
    if second_score <= 0:
        confidence = 0.90 if best_score >= 0.8 else 0.82
    else:
        confidence = min(0.93, 0.50 + 0.48 * best_score / (best_score + second_score))

    alternatives: list[dict] = []
    total = sum(scores.values())
    for intent, score in ranked[:3]:
        if score <= 0:
            continue
        share = score / total if total else 0
        alternatives.append(
            {
                "intent": intent,
                "confidence": round(confidence if intent == best_intent else share * (1 - confidence), 4),
                "matched": hits[intent][:4],
            }
        )
    return best_intent, round(confidence, 4), alternatives


class RuleBasedNLU:
    name = "rules"
    version = "rules-v1"

    def predict(self, text: str) -> NLUResult:
        started = time.perf_counter()
        if not text or not text.strip():
            return NLUResult(
                intent="other",
                confidence=0.0,
                entities=[],
                top_intents=[{"intent": "other", "confidence": 0.0}],
                model_version=self.version,
                source="rules",
            )
        intent, confidence, top_intents = classify_text(text)
        entities = extract_rule_entities(text)
        return NLUResult(
            intent=intent,
            confidence=confidence,
            entities=entities,
            top_intents=top_intents,
            model_version=self.version,
            calibrated=False,
            source="rules",
            latency_ms=(time.perf_counter() - started) * 1000,
        )
