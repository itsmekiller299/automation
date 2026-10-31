#!/usr/bin/env python3
"""Generate a reproducible, entity-annotated intent dataset.

The public starter ships with templated English + Hinglish utterances. It is a
seed/augmentation set, not a substitute for real anonymised support logs. Aim to
replace at least part of it with production utterances before trusting the
reported metrics.
"""

from __future__ import annotations

import argparse
import json
import random
import re
import sys
from datetime import UTC, datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from shared.catalog import PRODUCTS  # noqa: E402
from shared.labels import ENTITY_LABELS, INTENTS  # noqa: E402

ORDER_IDS = [f"ORD-{number}" for number in range(1000, 1251)]
PRODUCT_NAMES = [product["name"] for product in PRODUCTS]
PRODUCT_ALIASES = [alias for product in PRODUCTS for alias in product["aliases"]]
NAMES = [
    "Siva", "Anika", "Rahul", "Priya", "Maya", "Arjun", "Neha", "Kabir",
    "Isha", "Rohan", "Tara", "Vikram", "Zoya", "Aditya", "Meera", "Dev",
]
CITIES = ["Mumbai", "Pune", "Bengaluru", "Delhi", "Hyderabad", "Chennai", "Kolkata", "Jaipur"]
COLORS = ["sand", "olive", "charcoal", "ivory", "terracotta", "sage", "navy", "clay"]
DATES = [
    "today", "tomorrow", "next week", "next Monday", "this weekend",
    "10 October", "October 10", "2026-11-12", "12/11/2026", "kal", "parso",
]
REASONS = [
    "it is too large", "the colour is different", "I changed my mind",
    "it does not fit my room", "I ordered the wrong item", "the quality is not as expected",
]
ISSUES = [
    "a broken leg", "a deep scratch", "a missing part", "a torn cover",
    "a cracked shade", "the wrong colour", "a loose fitting",
]

TEMPLATES: dict[str, list[str]] = {
    "greeting": [
        "hi", "hello", "hey", "hey there", "hii", "hello team", "hi team",
        "good morning", "good afternoon", "good evening", "namaste", "namaskar",
        "hi, this is {name}", "hello, {name} here", "hey, {name} this side",
        "namaste, mera naam {name} hai", "{name} here, quick question",
        "hi, I need some help", "hello, are you there", "hey, can you help me",
        "hi from {city}", "hello from {city}", "good morning team, {name} here",
        "hi, just checking in", "hey, quick question", "hello, I have a question",
        "namaste team", "hi, hope you are well", "hey, are you open",
        "hello, can someone help", "hi, I wanted to ask something",
    ],
    "order_status": [
        "where is my order {order_id}", "can you track {order_id}",
        "what is the status of {order_id}", "has {order_id} shipped",
        "when will {order_id} arrive", "my order {order_id} is late",
        "track my order {order_id}", "any update on {order_id}",
        "is {order_id} out for delivery", "delivery status for {order_id}",
        "mera order {order_id} kahan hai", "{order_id} kab aayega",
        "order {order_id} ka update do", "delivery kab hogi {order_id}",
        "mera order {order_id} abhi tak nahi aaya", "{order_id} track karke batao",
        "where is my order", "order status please", "can you check my order status",
        "my order has not arrived yet", "when will my delivery arrive",
        "track my order", "I need a delivery update", "has my order shipped yet",
        "what is the delivery date", "order is showing delayed, why",
        "mera order kahan hai", "order kab aayega", "delivery update chahiye",
        "order abhi tak nahi mila", "status batao please",
        "can you find order {order_id}", "please check {order_id} for me",
        "I want an update on {order_id}", "is {order_id} delayed",
        "{order_id} delivery date kya hai", "order {order_id} kahan pahuncha",
        "where is my {product} order", "my {product} has not arrived",
        "I ordered a {product}, where is it", "will {order_id} arrive by {date}",
        "can you deliver by {date}", "{date} tak order {order_id} aa jayega",
        "I need delivery before {date}",
    ],
    "return_refund": [
        "I want to return {product}", "how do I return order {order_id}",
        "I need a refund for {order_id}", "can I exchange {product}",
        "what is the return policy for {product}", "I want to send {product} back",
        "refund status for {order_id}", "cancel order {order_id}",
        "can I cancel {order_id} and get a refund", "I received the wrong item, I want a refund",
        "mera {product} wapas karna hai", "refund chahiye order {order_id}",
        "paisa wapas kab milega", "order {order_id} cancel karna hai",
        "{product} return kaise karu", "exchange karna hai {product}",
        "return policy kya hai", "I want my money back", "please process a refund",
        "the item is not suitable, can I return it", "I changed my mind, can I return {product}",
        "how many days do I have to return {product}", "is {product} returnable",
        "I want to return my order", "I need to return an item",
        "can I get a refund on {order_id}", "my return is late, where is my refund",
        "return my order {order_id}", "I want to exchange my {product}",
        "return {order_id} and refund me", "kya main {product} return kar sakta hoon",
        "refund kitne din mein aayega", "order {order_id} wapas karna hai",
        "I want to cancel my order", "can I return a sale item",
        "how do I start a return", "the return label did not arrive",
        "I need the refund by {date}", "can I return {product} before {date}",
        "{date} tak return kar sakta hoon kya",
    ],
    "product_info": [
        "tell me about {product}", "what material is {product} made of",
        "what are the dimensions of {product}", "is {product} available in {color}",
        "how do I care for {product}", "does {product} come assembled",
        "what is included with {product}", "is {product} in stock",
        "how heavy is {product}", "what size is {product}",
        "{product} ka material kya hai", "{product} kitne inch ka hai",
        "{product} kaise clean kare", "{product} assembled aata hai",
        "{product} ka size kya hai", "{product} ka colour kya hai",
        "can you share the specifications of {product}", "tell me the features of {product}",
        "is {product} suitable for a small room", "what fabric is used in {product}",
        "does {product} need assembly", "what is the warranty on {product}",
        "is {product} available now", "can I see more details about {product}",
        "how do I use {product}", "what is the weight capacity of {product}",
        "is {product} easy to clean", "what colours does {product} come in",
        "{product} ke baare mein batao", "{product} ka detail bhejo",
        "does {product} match the photo", "what is the finish on {product}",
        "is the {product} cover removable", "how many pieces are in {product}",
        "what are the care instructions for {product}", "is {product} child safe",
        "will {product} be back in stock by {date}", "can {product} be delivered by {date}",
        "{date} tak {product} mil jayega",
    ],
    "pricing": [
        "how much is {product}", "what is the price of {product}",
        "what does {product} cost", "is there a discount on {product}",
        "any offers on {product}", "price of {product} please",
        "{product} kitne ka hai", "{product} ka price kya hai",
        "{product} par discount milega", "{product} ka rate batao",
        "do you have student discount", "do you price match",
        "are there any current offers", "what is your cheapest {product}",
        "how much for {product} in {city}", "is {product} on sale",
        "can I get a coupon for {product}", "what is the best price for {product}",
        "how much does the {product} cost today", "is the {product} price negotiable",
        "price kya chal raha hai {product} ka", "{product} sasta milega",
        "koi offer hai kya", "discount code chahiye", "student discount available hai",
        "how much is shipping", "are prices inclusive of tax",
        "what is the total price of {product}", "do you offer bulk pricing",
        "can you give me a quote for {product}", "is there a sale this week",
        "{product} ka final price kya hoga", "price match karte ho kya",
        "is the {product} price valid until {date}", "{date} tak offer chalega kya",
    ],
    "complaint": [
        "my {product} arrived damaged", "order {order_id} is late again",
        "I received the wrong item", "{product} is broken",
        "this is unacceptable", "the {product} stopped working",
        "worst delivery experience", "my {product} has {issue}",
        "mera {product} kharab aaya", "order {order_id} galat aaya",
        "bakwas quality", "I am frustrated with order {order_id}",
        "the {product} looks used", "my order arrived with {issue}",
        "I have complained twice already", "this is the worst service",
        "the courier damaged my {product}", "I want to report a problem with {order_id}",
        "{product} is missing from the box", "the colour is completely wrong",
        "I am very disappointed with {product}", "order {order_id} is still not here",
        "the packaging was torn and {product} is scratched", "this product feels cheap",
        "I was charged twice", "my refund still has not arrived",
        "the {product} does not match the description", "I received a used {product}",
        "order {order_id} has {issue}", "this is ridiculous, {product} is damaged",
        "mera order {order_id} kharab aaya", "{product} mein problem hai",
        "quality bahut kharab hai", "mujhe galat item mila",
        "delivery bahut late ho gayi", "product toot gaya",
        "I am fed up with this order", "please fix this immediately",
        "I was promised delivery by {date}", "{date} tak order nahi aaya",
        "the replacement was due by {date}",
    ],
    "human_agent": [
        "I want to talk to a human", "connect me to an agent",
        "customer care please", "real person please", "can I speak to a manager",
        "I need a human representative", "transfer me to support",
        "agent se baat karni hai", "insaan se baat karwao",
        "customer care se connect karo", "manager se baat karni hai",
        "please call me", "I want a person, not a bot",
        "get me someone from your team", "can a human help me",
        "I need to speak with someone now", "support team please",
        "connect me to customer service", "I want to escalate this",
        "let me talk to a real agent", "human support chahiye",
        "koi insaan bulao", "agent available hai kya",
        "mujhe manager se baat karni hai", "please transfer this chat",
        "I need help from your team", "can you connect me to a person",
        "I do not want to talk to a bot", "someone call me please",
        "I need urgent human help", "send this to a supervisor",
        "talk to a representative", "I want to file a complaint with a person",
    ],
    "goodbye": [
        "thanks", "thank you", "bye", "goodbye", "that's all",
        "no more questions", "have a good day", "see you", "done for now",
        "shukriya", "dhanyavad", "theek hai bye", "chalta hoon",
        "phir milte hain", "thanks for your help", "great, thank you",
        "all good, bye", "I am done", "that is everything", "no thanks, bye",
        "thanks, I will wait", "okay thank you", "appreciate it, bye",
        "thanks team", "bye bye", "talk later", "I will get back to you",
        "that helps, thanks", "perfect, thank you", "ok bye",
        "shukriya team", "theek hai, thanks", "bas itna hi",
        "aur kuch nahi chahiye", "thanks, goodbye",
    ],
    "other": [
        "what is the weather today", "tell me a joke", "who are you",
        "what is your name", "can you write code", "what is the cricket score",
        "do you follow politics", "sing a song", "order me a pizza",
        "what is the capital of France", "how old are you", "are you human",
        "what is your favourite colour", "can you book a cab",
        "what time is it", "tell me a story", "do you like cricket",
        "what is the meaning of life", "can you translate this", "how do I cook pasta",
        "what is the stock market doing", "play some music", "send me a meme",
        "what is two plus two", "who is the prime minister", "what is AI",
        "can you help with my homework", "what is the news", "recommend a movie",
        "how far is the moon", "mausam kaisa hai", "ek joke sunao",
        "tum kaun ho", "aapka naam kya hai", "cricket score batao",
        "kya aap gaana suna sakte ho", "mujhe pizza order kar do",
        "aaj ka news kya hai", "movie suggest karo", "tum insaan ho kya",
    ],
}

PREFIXES = {
    "greeting": ["", "", "", "", "hello, ", "hey, ", "namaste, ", "good day, "],
    "order_status": ["", "", "", "hi, ", "hello, ", "please ", "quick help: ", "urgent: "],
    "return_refund": ["", "", "", "hi, ", "hello, ", "please ", "urgent: ", "I need help: "],
    "product_info": ["", "", "", "hi, ", "hello, ", "quick question: ", "please ", "I wanted to ask: "],
    "pricing": ["", "", "", "hi, ", "hello, ", "quick question: ", "please ", "urgent: "],
    "complaint": ["", "", "", "hi, ", "hello, ", "urgent: ", "again, ", "seriously, "],
    "human_agent": ["", "", "", "hi, ", "hello, ", "urgent: ", "right now, ", "team, "],
    "goodbye": ["", "", "", "okay, ", "alright, ", "well, ", "thanks, ", "hi, "],
    "other": ["", "", "", "hey, ", "hello, ", "random question: ", "quick one: ", "just wondering, "],
}

SUFFIXES = [
    "", "", "", "", " please.", " thanks.", " asap.", " urgently.",
    " thank you.", " kripya.", " jaldi.", " please help.",
]

PUNCTUATION = ["", "", "?", "!", "."]


def _slot_value(slot: str, rng: random.Random) -> tuple[str, str | None]:
    if slot == "product":
        if rng.random() < 0.35:
            alias = rng.choice(PRODUCT_ALIASES)
            canonical = next(
                product["name"]
                for product in PRODUCTS
                if alias in {product["name"].lower(), *[a.lower() for a in product.get("aliases", [])]}
            )
            return alias, canonical
        return rng.choice(PRODUCT_NAMES), None
    if slot == "order_id":
        return rng.choice(ORDER_IDS), None
    if slot == "date":
        return rng.choice(DATES), None
    if slot == "name":
        return rng.choice(NAMES), None
    if slot == "city":
        return rng.choice(CITIES), None
    if slot == "color":
        return rng.choice(COLORS), None
    if slot == "reason":
        return rng.choice(REASONS), None
    if slot == "issue":
        return rng.choice(ISSUES), None
    raise ValueError(f"Unknown slot: {slot}")


SLOT_ENTITY_TYPES = {
    "product": "PRODUCT",
    "order_id": "ORDER_ID",
    "date": "DATE",
}


def render_template(template: str, rng: random.Random) -> tuple[str, list[dict]]:
    """Render slots while preserving exact character offsets for entities."""
    output: list[str] = []
    entities: list[dict] = []
    cursor = 0
    for match in re.finditer(r"\{(\w+)\}", template):
        literal = template[cursor : match.start()]
        output.append(literal)
        slot = match.group(1)
        value, canonical = _slot_value(slot, rng)
        start = sum(len(part) for part in output)
        output.append(value)
        entity_type = SLOT_ENTITY_TYPES.get(slot)
        if entity_type:
            entities.append(
                {
                    "type": entity_type,
                    "value": canonical or value,
                    "start": start,
                    "end": start + len(value),
                }
            )
        cursor = match.end()
    output.append(template[cursor:])
    return "".join(output), entities


def augment(
    template: str,
    intent: str,
    rng: random.Random,
) -> tuple[str, list[dict]]:
    prefix = rng.choice(PREFIXES[intent])
    suffix = rng.choice(SUFFIXES)
    text, entities = render_template(template, rng)
    shift = len(prefix)
    text = prefix + text
    text = (
        text[:-1] + suffix
        if suffix and text.endswith((".", "?", "!"))
        else text + suffix
    )
    punctuation = rng.choice(PUNCTUATION)
    if punctuation and not text.endswith((".", "?", "!")):
        text += punctuation
    if not text:
        text = "hello"
    text = text[0].upper() + text[1:]
    entities = [
        {**entity, "start": entity["start"] + shift, "end": entity["end"] + shift}
        for entity in entities
    ]
    return text, entities


def generate(per_intent: int, seed: int) -> dict[str, list[dict]]:
    rng = random.Random(seed)
    dataset: dict[str, list[dict]] = {}
    for intent in INTENTS:
        rows: list[dict] = []
        seen: set[str] = set()
        attempts = 0
        max_attempts = per_intent * 60
        while len(rows) < per_intent and attempts < max_attempts:
            attempts += 1
            template = rng.choice(TEMPLATES[intent])
            text, entities = augment(template, intent, rng)
            key = text.strip().lower()
            if key in seen:
                continue
            seen.add(key)
            rows.append(
                {
                    "id": f"{intent}-{len(rows):05d}",
                    "text": text,
                    "intent": intent,
                    "entities": entities,
                }
            )
        if len(rows) < per_intent:
            raise RuntimeError(
                f"Could only generate {len(rows)} unique examples for {intent}; "
                "add templates or lower --per-intent."
            )
        dataset[intent] = rows
        print(f"  {intent:<14} {len(rows):>5} utterances ({attempts} attempts)")
    return dataset


def split_dataset(dataset: dict[str, list[dict]], seed: int) -> tuple[list[dict], list[dict], list[dict]]:
    rng = random.Random(seed + 1)
    train: list[dict] = []
    val: list[dict] = []
    test: list[dict] = []
    for rows in dataset.values():
        shuffled = rows[:]
        rng.shuffle(shuffled)
        total = len(shuffled)
        val_count = max(1, round(total * 0.10))
        test_count = max(1, round(total * 0.10))
        test.extend(shuffled[:test_count])
        val.extend(shuffled[test_count : test_count + val_count])
        train.extend(shuffled[test_count + val_count :])
    rng.shuffle(train)
    rng.shuffle(val)
    rng.shuffle(test)
    return train, val, test


def write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate the intent/entity seed dataset")
    parser.add_argument("--per-intent", type=int, default=1500)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument(
        "--output-dir", type=Path, default=PROJECT_ROOT / "ml" / "data" / "splits"
    )
    args = parser.parse_args()

    print(f"Generating {args.per_intent} examples per intent (seed={args.seed})")
    dataset = generate(args.per_intent, args.seed)
    train, val, test = split_dataset(dataset, args.seed)

    write_jsonl(args.output_dir / "train.jsonl", train)
    write_jsonl(args.output_dir / "val.jsonl", val)
    write_jsonl(args.output_dir / "test.jsonl", test)

    stats = {
        "generated_at": datetime.now(UTC).isoformat(),
        "seed": args.seed,
        "requested_per_intent": args.per_intent,
        "total": len(train) + len(val) + len(test),
        "splits": {"train": len(train), "val": len(val), "test": len(test)},
        "per_intent": {intent: len(rows) for intent, rows in dataset.items()},
        "intents": INTENTS,
        "entity_labels": ENTITY_LABELS,
        "note": (
            "Templated seed data with English/Hinglish variants. Replace or augment with "
            "consented, anonymised production utterances before relying on test metrics."
        ),
    }
    (args.output_dir.parent / "dataset_stats.json").write_text(
        json.dumps(stats, indent=2), encoding="utf-8"
    )
    print(
        f"Wrote {len(train)} train / {len(val)} val / {len(test)} test rows to {args.output_dir}"
    )


if __name__ == "__main__":
    main()
