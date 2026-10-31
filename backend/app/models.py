from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


def utcnow() -> datetime:
    """Naive UTC, used consistently on SQLite and PostgreSQL."""
    return datetime.now(UTC).replace(tzinfo=None)


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex}"


class Customer(Base):
    __tablename__ = "customers"
    __table_args__ = (
        UniqueConstraint("channel", "external_id", name="uq_customer_channel_external"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: new_id("cus"))
    tenant_id: Mapped[str | None] = mapped_column(
        ForeignKey("tenants.id", ondelete="SET NULL"), index=True
    )
    channel: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    external_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    display_name: Mapped[str | None] = mapped_column(String(255))
    opted_in: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)

    conversations: Mapped[list[Conversation]] = relationship(
        back_populates="customer", cascade="all, delete-orphan", passive_deletes=True
    )


class Conversation(Base):
    __tablename__ = "conversations"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: new_id("cnv"))
    tenant_id: Mapped[str | None] = mapped_column(
        ForeignKey("tenants.id", ondelete="SET NULL"), index=True
    )
    customer_id: Mapped[str] = mapped_column(
        ForeignKey("customers.id", ondelete="CASCADE"), nullable=False, index=True
    )
    channel: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(32), default="bot", nullable=False, index=True)
    last_intent: Mapped[str | None] = mapped_column(String(64))
    last_confidence: Mapped[float | None] = mapped_column(Float)
    assigned_agent: Mapped[str | None] = mapped_column(String(255))
    bot_identified: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    last_inbound_at: Mapped[datetime | None] = mapped_column(DateTime)
    last_outbound_at: Mapped[datetime | None] = mapped_column(DateTime)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=utcnow, onupdate=utcnow, nullable=False
    )

    customer: Mapped[Customer] = relationship(back_populates="conversations")
    messages: Mapped[list[Message]] = relationship(
        back_populates="conversation",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="Message.created_at",
    )
    handoffs: Mapped[list[Handoff]] = relationship(
        back_populates="conversation", cascade="all, delete-orphan", passive_deletes=True
    )


class Message(Base):
    __tablename__ = "messages"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: new_id("msg"))
    conversation_id: Mapped[str] = mapped_column(
        ForeignKey("conversations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    direction: Mapped[str] = mapped_column(
        String(16), nullable=False, index=True
    )  # inbound|outbound
    channel: Mapped[str] = mapped_column(String(32), nullable=False)
    text: Mapped[str] = mapped_column(Text, default="", nullable=False)
    message_type: Mapped[str] = mapped_column(String(32), default="text", nullable=False)
    intent: Mapped[str | None] = mapped_column(String(64), index=True)
    confidence: Mapped[float | None] = mapped_column(Float)
    entities: Mapped[list] = mapped_column(JSON, default=list)
    external_message_id: Mapped[str | None] = mapped_column(String(255), unique=True)
    delivery_status: Mapped[str | None] = mapped_column(String(32))
    meta: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=utcnow, nullable=False, index=True
    )

    conversation: Mapped[Conversation] = relationship(back_populates="messages")


Index("ix_messages_conversation_created", Message.conversation_id, Message.created_at)


class PredictionLog(Base):
    __tablename__ = "prediction_logs"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: new_id("prd"))
    conversation_id: Mapped[str | None] = mapped_column(
        ForeignKey("conversations.id", ondelete="CASCADE"), index=True
    )
    message_id: Mapped[str | None] = mapped_column(
        ForeignKey("messages.id", ondelete="CASCADE"), index=True
    )
    intent: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    confidence: Mapped[float] = mapped_column(Float, nullable=False)
    model_version: Mapped[str] = mapped_column(String(64), default="rules-v1", nullable=False)
    top_intents: Mapped[list] = mapped_column(JSON, default=list)
    entities: Mapped[list] = mapped_column(JSON, default=list)
    corrected_intent: Mapped[str | None] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=utcnow, nullable=False, index=True
    )


class Handoff(Base):
    __tablename__ = "handoffs"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: new_id("hnd"))
    conversation_id: Mapped[str] = mapped_column(
        ForeignKey("conversations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    reason: Mapped[str] = mapped_column(String(64), nullable=False)
    priority: Mapped[str] = mapped_column(String(16), default="normal", nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(16), default="open", nullable=False, index=True)
    assigned_to: Mapped[str | None] = mapped_column(String(255))
    note: Mapped[str | None] = mapped_column(Text)
    source: Mapped[str] = mapped_column(String(32), default="bot", nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=utcnow, nullable=False, index=True
    )
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime)

    conversation: Mapped[Conversation] = relationship(back_populates="handoffs")


class FeedbackRecord(Base):
    __tablename__ = "feedback_records"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: new_id("fbk"))
    prediction_id: Mapped[str | None] = mapped_column(
        ForeignKey("prediction_logs.id", ondelete="CASCADE"), index=True
    )
    message_id: Mapped[str | None] = mapped_column(
        ForeignKey("messages.id", ondelete="CASCADE"), index=True
    )
    utterance: Mapped[str] = mapped_column(Text, nullable=False)
    predicted_intent: Mapped[str] = mapped_column(String(64), nullable=False)
    corrected_intent: Mapped[str] = mapped_column(String(64), nullable=False)
    agent: Mapped[str | None] = mapped_column(String(255))
    status: Mapped[str] = mapped_column(String(16), default="pending", nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=utcnow, nullable=False, index=True
    )


class OrderStatusEvent(Base):
    """Small audit trail for order lookups; never stores payment data."""

    __tablename__ = "order_lookup_events"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: new_id("ord"))
    conversation_id: Mapped[str | None] = mapped_column(
        ForeignKey("conversations.id", ondelete="CASCADE"), index=True
    )
    order_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    found: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    source: Mapped[str] = mapped_column(String(32), default="orders_api", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)


class DriftSnapshot(Base):
    __tablename__ = "drift_snapshots"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    window_start: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    window_end: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    sample_size: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    avg_confidence: Mapped[float | None] = mapped_column(Float)
    distribution: Mapped[dict] = mapped_column(JSON, default=dict)
    drift_score: Mapped[float | None] = mapped_column(Float)
    flagged: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)


class Tenant(Base):
    """A customer business using the portal.

    Automation is deliberately off until the owner signs in, so a workspace
    cannot start replying to end customers before it has been activated.
    """

    __tablename__ = "tenants"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: new_id("tnt"))
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    slug: Mapped[str] = mapped_column(String(120), nullable=False, unique=True, index=True)
    plan: Mapped[str] = mapped_column(String(32), default="starter", nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="active", nullable=False)
    automation_enabled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    activated_at: Mapped[datetime | None] = mapped_column(DateTime)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)

    users: Mapped[list[PortalUser]] = relationship(
        back_populates="tenant", cascade="all, delete-orphan", passive_deletes=True
    )
    channels: Mapped[list[ChannelConnection]] = relationship(
        back_populates="tenant", cascade="all, delete-orphan", passive_deletes=True
    )


class PortalUser(Base):
    __tablename__ = "portal_users"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: new_id("usr"))
    tenant_id: Mapped[str] = mapped_column(
        ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True
    )
    email: Mapped[str | None] = mapped_column(String(320), unique=True, index=True)
    phone: Mapped[str | None] = mapped_column(String(32), unique=True, index=True)
    full_name: Mapped[str] = mapped_column(String(255), nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[str] = mapped_column(String(32), default="owner", nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    welcome_opt_in: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    welcome_opt_in_at: Mapped[datetime | None] = mapped_column(DateTime)
    phone_verified: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    phone_verified_at: Mapped[datetime | None] = mapped_column(DateTime)
    otp_hash: Mapped[str | None] = mapped_column(String(128))
    otp_expires_at: Mapped[datetime | None] = mapped_column(DateTime)
    otp_attempts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)

    tenant: Mapped[Tenant] = relationship(back_populates="users")
    sessions: Mapped[list[PortalSession]] = relationship(
        back_populates="user", cascade="all, delete-orphan", passive_deletes=True
    )


class PortalSession(Base):
    __tablename__ = "portal_sessions"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: new_id("psn"))
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    user_id: Mapped[str] = mapped_column(
        ForeignKey("portal_users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    tenant_id: Mapped[str] = mapped_column(
        ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime)
    ip_address: Mapped[str | None] = mapped_column(String(64))
    user_agent: Mapped[str | None] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)

    user: Mapped[PortalUser] = relationship(back_populates="sessions")


class ChannelConnection(Base):
    __tablename__ = "channel_connections"
    __table_args__ = (
        UniqueConstraint("tenant_id", "channel", name="uq_channel_tenant"),
        UniqueConstraint("channel", "external_account_id", name="uq_channel_external_account"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: new_id("chn"))
    tenant_id: Mapped[str] = mapped_column(
        ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True
    )
    channel: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    external_account_id: Mapped[str] = mapped_column(String(255), nullable=False)
    display_name: Mapped[str | None] = mapped_column(String(255))
    status: Mapped[str] = mapped_column(String(32), default="connected", nullable=False)
    access_token_cipher: Mapped[str | None] = mapped_column(Text)
    token_expires_at: Mapped[datetime | None] = mapped_column(DateTime)
    scopes: Mapped[str | None] = mapped_column(Text)
    meta: Mapped[dict] = mapped_column(JSON, default=dict)
    connected_by_user_id: Mapped[str | None] = mapped_column(
        ForeignKey("portal_users.id", ondelete="SET NULL")
    )
    connected_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=utcnow, onupdate=utcnow, nullable=False
    )

    tenant: Mapped[Tenant] = relationship(back_populates="channels")


class PortalEvent(Base):
    __tablename__ = "portal_events"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: new_id("evt"))
    tenant_id: Mapped[str] = mapped_column(
        ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True
    )
    user_id: Mapped[str | None] = mapped_column(
        ForeignKey("portal_users.id", ondelete="SET NULL"), index=True
    )
    session_id: Mapped[str | None] = mapped_column(
        ForeignKey("portal_sessions.id", ondelete="SET NULL")
    )
    event_type: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(32), default="ok", nullable=False)
    channel: Mapped[str | None] = mapped_column(String(32))
    detail: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=utcnow, nullable=False, index=True
    )
