"""Label definitions shared by training and inference.

Keeping these in one place prevents the classic production bug where the
training label order no longer matches the inference label order.
"""

INTENTS = [
    "greeting",
    "order_status",
    "return_refund",
    "product_info",
    "pricing",
    "complaint",
    "human_agent",
    "goodbye",
    "other",
]

INTENT_DESCRIPTIONS = {
    "greeting": "Customer opens the conversation or says hello.",
    "order_status": "Customer asks where an order is or what state it is in.",
    "return_refund": "Customer wants to return an item or get a refund.",
    "product_info": "Customer asks about product features, materials, sizing, or availability.",
    "pricing": "Customer asks how much something costs or about discounts.",
    "complaint": "Customer reports a problem, damaged item, poor experience, or is upset.",
    "human_agent": "Customer explicitly asks for a person or support agent.",
    "goodbye": "Customer ends the conversation or says thanks.",
    "other": "Out of scope, small talk, or anything the NLU is unsure about.",
}

INTENT2ID = {label: idx for idx, label in enumerate(INTENTS)}
ID2INTENT = {idx: label for label, idx in INTENT2ID.items()}

ENTITY_LABELS = [
    "O",
    "B-ORDER_ID",
    "I-ORDER_ID",
    "B-PRODUCT",
    "I-PRODUCT",
    "B-DATE",
    "I-DATE",
]

ENTITY2ID = {label: idx for idx, label in enumerate(ENTITY_LABELS)}
ID2ENTITY = {idx: label for label, idx in ENTITY2ID.items()}

# Runtime states for a conversation. Kept as strings so SQLite and Postgres
# behave identically and future states do not require a migration.
CONVERSATION_OPEN = "bot"
CONVERSATION_NEEDS_HUMAN = "needs_human"
CONVERSATION_RESOLVED = "resolved"

HANDOFF_OPEN = "open"
HANDOFF_ASSIGNED = "assigned"
HANDOFF_RESOLVED = "resolved"
