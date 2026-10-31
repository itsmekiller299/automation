from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator

from shared.labels import INTENTS


class CustomerOut(BaseModel):
    id: str
    channel: str
    external_id: str
    display_name: str | None = None
    opted_in: bool
    created_at: datetime
    last_seen_at: datetime


class MessageOut(BaseModel):
    id: str
    conversation_id: str
    direction: str
    channel: str
    text: str
    message_type: str
    intent: str | None = None
    confidence: float | None = None
    entities: list = Field(default_factory=list)
    external_message_id: str | None = None
    delivery_status: str | None = None
    meta: dict = Field(default_factory=dict)
    created_at: datetime


class HandoffOut(BaseModel):
    id: str
    conversation_id: str
    channel: str | None = None
    reason: str
    priority: str
    status: str
    assigned_to: str | None = None
    note: str | None = None
    source: str
    created_at: datetime
    resolved_at: datetime | None = None
    customer_name: str | None = None
    last_message: str | None = None


class ConversationSummary(BaseModel):
    id: str
    channel: str
    status: str
    customer: CustomerOut
    last_intent: str | None = None
    last_confidence: float | None = None
    assigned_agent: str | None = None
    bot_identified: bool
    last_message_preview: str | None = None
    last_message_at: datetime | None = None
    created_at: datetime
    updated_at: datetime
    open_handoff: HandoffOut | None = None


class ConversationDetail(ConversationSummary):
    messages: list[MessageOut] = Field(default_factory=list)


class ReplyIn(BaseModel):
    text: str = Field(min_length=1, max_length=4000)
    agent: str | None = Field(default=None, max_length=255)


class HandoffIn(BaseModel):
    reason: str = Field(default="agent_requested", max_length=64)
    priority: Literal["low", "normal", "high", "urgent"] = "normal"
    note: str | None = Field(default=None, max_length=2000)
    agent: str | None = Field(default=None, max_length=255)


class ResolveIn(BaseModel):
    agent: str | None = None
    note: str | None = None


class AssignIn(BaseModel):
    agent: str = Field(min_length=1, max_length=255)


class FeedbackIn(BaseModel):
    corrected_intent: str
    agent: str | None = None

    @field_validator("corrected_intent")
    @classmethod
    def _valid_intent(cls, value: str) -> str:
        if value not in INTENTS:
            raise ValueError(f"corrected_intent must be one of {INTENTS}")
        return value


class DeleteCustomerIn(BaseModel):
    channel: Literal["whatsapp", "instagram"] | None = None
    external_id: str | None = None
    customer_id: str | None = None
    confirm: bool = False

    @field_validator("confirm")
    @classmethod
    def _must_confirm(cls, value: bool) -> bool:
        if not value:
            raise ValueError("Set confirm=true to permanently delete customer data")
        return value


class OverviewOut(BaseModel):
    days: int
    conversations: int
    active_conversations: int
    needs_human: int
    inbound_messages: int
    outbound_messages: int
    bot_resolved: int
    handoffs: int
    handoff_rate: float
    resolution_rate: float
    avg_confidence: float | None
    open_handoffs: int
    pending_feedback: int


class IntentStat(BaseModel):
    intent: str
    count: int
    share: float
    avg_confidence: float | None


class ConfidenceBucket(BaseModel):
    bucket: str
    count: int


class VolumePoint(BaseModel):
    date: str
    inbound: int
    outbound: int


class DriftOut(BaseModel):
    flagged: bool
    current_window: dict
    previous_window: dict
    total_variation: float
    confidence_delta: float
    intent_shift: dict
    thresholds: dict
    note: str
