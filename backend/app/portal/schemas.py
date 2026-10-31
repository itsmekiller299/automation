from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator

ChannelName = Literal["whatsapp", "instagram"]


class RegisterIn(BaseModel):
    business_name: str = Field(min_length=2, max_length=255)
    full_name: str = Field(min_length=2, max_length=255)
    email: str | None = Field(default=None, max_length=320)
    phone: str | None = Field(default=None, max_length=32)
    password: str = Field(min_length=10, max_length=256)
    welcome_opt_in: bool = False

    @field_validator("email")
    @classmethod
    def _email_shape(cls, value: str | None) -> str | None:
        if value is None or not value.strip():
            return None
        value = value.strip().lower()
        if "@" not in value or "." not in value.rsplit("@", 1)[-1]:
            raise ValueError("Enter a valid email address")
        return value

    @model_validator(mode="after")
    def _identifier_required(self) -> RegisterIn:
        if not self.email and not self.phone:
            raise ValueError("Provide an email address or a phone number")
        return self


class LoginIn(BaseModel):
    identifier: str = Field(min_length=3, max_length=320)
    password: str = Field(min_length=1, max_length=256)


class VerifyPhoneIn(BaseModel):
    code: str = Field(min_length=6, max_length=6)

    @field_validator("code")
    @classmethod
    def _digits(cls, value: str) -> str:
        if not value.isdigit():
            raise ValueError("Enter the 6-digit code")
        return value


class PhoneUpdateIn(BaseModel):
    phone: str = Field(min_length=8, max_length=32)
    password: str = Field(min_length=1, max_length=256)


class ChannelConnectIn(BaseModel):
    mode: Literal["oauth", "demo"] = "oauth"
    authorization_code: str | None = Field(default=None, max_length=2048)
    state: str | None = Field(default=None, max_length=4096)
    external_account_id: str | None = Field(default=None, max_length=255)
    display_name: str | None = Field(default=None, max_length=255)
    waba_id: str | None = Field(default=None, max_length=255)
    scopes: str | None = Field(default=None, max_length=1000)

    @model_validator(mode="after")
    def _mode_requirements(self) -> ChannelConnectIn:
        if self.mode == "oauth" and not self.authorization_code:
            raise ValueError("authorization_code is required for OAuth connections")
        if self.mode == "demo" and not self.external_account_id:
            raise ValueError("external_account_id is required for demo connections")
        return self


class TenantOut(BaseModel):
    id: str
    name: str
    slug: str
    plan: str
    automation_enabled: bool
    activated_at: datetime | None = None


class PortalUserOut(BaseModel):
    id: str
    full_name: str
    email: str | None = None
    phone: str | None = None
    role: str
    welcome_opt_in: bool
    phone_verified: bool
    last_login_at: datetime | None = None


class ChannelOut(BaseModel):
    channel: ChannelName
    external_account_id: str
    display_name: str | None = None
    status: str
    connected_at: datetime
    token_expires_at: datetime | None = None


class PortalEventOut(BaseModel):
    id: str
    event_type: str
    status: str
    channel: str | None = None
    detail: dict = Field(default_factory=dict)
    created_at: datetime


class ActivationOut(BaseModel):
    status: Literal["sent", "blocked", "failed", "skipped"]
    reason: str | None = None
    channel: str | None = None


class AuthOut(BaseModel):
    token: str
    expires_at: datetime
    user: PortalUserOut
    tenant: TenantOut
    activation: ActivationOut | None = None
    phone_verification_required: bool = False


class MeOut(BaseModel):
    user: PortalUserOut
    tenant: TenantOut
    channels: list[ChannelOut]
    recent_events: list[PortalEventOut]


class OAuthUrlOut(BaseModel):
    channel: ChannelName
    configured: bool
    url: str | None = None
    mock_allowed: bool
    message: str | None = None


class PortalConfigOut(BaseModel):
    enabled: bool
    meta_oauth_configured: bool
    mock_channel_connect: bool
    welcome_template: str
    brand: str


class PhoneVerificationOut(BaseModel):
    status: Literal["sent", "already_verified", "unavailable", "rate_limited"]
    phone: str | None = None
    dev_code: str | None = None
    message: str | None = None
