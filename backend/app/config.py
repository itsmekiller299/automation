from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict

PROJECT_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(".env", "../.env"),
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # --- app ---
    app_name: str = "Orbit Auto-Reply"
    environment: Literal["development", "staging", "production", "test"] = "development"
    debug: bool = False
    log_level: str = "INFO"
    api_host: str = "0.0.0.0"
    api_port: int = 8000
    public_base_url: str = "http://localhost:8000"
    dashboard_base_url: str = "http://localhost:5173"
    cors_origins: str = "http://localhost:5173,http://localhost:4173"
    admin_api_key: str = ""
    brand_name: str = "Aurora Living"
    data_retention_days: int = 180
    portal_enabled: bool = True

    # --- storage ---
    database_url: str = "sqlite:///./data/app.db"
    redis_url: str = "redis://localhost:6379/0"
    queue_backend: Literal["celery", "inline"] = "celery"
    celery_task_always_eager: bool = False
    session_ttl_seconds: int = 86_400

    # --- Meta / webhooks ---
    app_secret: str = ""
    verify_token: str = "change-me-verify-token"
    allow_unsigned_webhooks: bool = False
    whatsapp_token: str = ""
    phone_number_id: str = ""
    whatsapp_business_account_id: str = ""
    whatsapp_api_version: str = "v21.0"
    whatsapp_template_name: str = "agent_handoff"
    whatsapp_template_language: str = "en_US"
    whatsapp_window_hours: int = 24
    ig_page_token: str = ""
    ig_business_account_id: str = ""
    ig_api_version: str = "v21.0"
    graph_base_url: str = "https://graph.facebook.com"
    instagram_window_hours: int = 24

    # --- customer portal / multi-tenant auth ---
    # Fernet key material for channel tokens. Falls back to APP_SECRET in
    # development; production deployments must set a dedicated value.
    portal_encryption_key: str = ""
    portal_session_hours: int = 12
    portal_login_max_attempts: int = 10
    portal_login_window_seconds: int = 600
    portal_password_min_length: int = 10
    # Local/demo only. Ignored in production; never collect Meta passwords.
    portal_allow_mock_channel_connect: bool = True
    portal_public_url: str = "http://localhost:5173"
    # Meta OAuth / Embedded Signup app used to connect WhatsApp and Instagram.
    portal_meta_app_id: str = ""
    portal_meta_app_secret: str = ""
    portal_meta_config_id: str = ""
    portal_oauth_redirect_uri: str = ""
    # Template used for the login confirmation. It must be approved in Meta.
    portal_welcome_template_name: str = "portal_login_confirmation"
    portal_welcome_template_language: str = "en_US"
    portal_assignment_template_name: str = "agent_assigned"
    portal_assignment_template_language: str = "en_US"
    # Phone ownership must be proven before proactive messages are allowed.
    # `dev` surfaces the OTP in local API responses; `webhook` POSTs to the URL.
    portal_otp_delivery: Literal["dev", "webhook", "disabled"] = "dev"
    portal_otp_webhook_url: str = ""
    portal_otp_ttl_seconds: int = 600
    portal_otp_max_attempts: int = 5

    # --- NLU ---
    nlu_backend: Literal["auto", "rules", "transformer"] = "auto"
    nlu_model_dir: str = "ml/artifacts/intent-model"
    nlu_onnx_path: str = "ml/artifacts/intent-model/model.onnx"
    nlu_model_version: str = "rules-v1"
    nlu_evaluation_path: str = "ml/artifacts/evaluation/evaluation.json"
    intent_confidence_threshold: float = 0.80
    max_fallbacks: int = 2
    max_window_attempts: int = 2

    # --- RAG ---
    rag_backend: Literal["auto", "lexical", "semantic"] = "auto"
    embedding_model: str = "sentence-transformers/all-MiniLM-L6-v2"
    embedding_local_only: bool = True
    faq_path: str = "ml/data/faqs.jsonl"
    rag_top_k: int = 3
    rag_min_score: float = 0.12
    rag_min_semantic_score: float = 0.38

    # --- optional LLM ---
    # `template` is deliberately the default: no vendor is chosen for you.
    # `anthropic` rewrites verified answers through Claude; ungrounded output is
    # rejected and the template answer is sent instead.
    llm_provider: Literal["template", "none", "anthropic"] = "template"
    llm_api_key: str = ""
    llm_model: str = "claude-sonnet-4-5"
    llm_base_url: str = "https://api.anthropic.com"
    llm_anthropic_version: str = "2023-06-01"
    llm_timeout_seconds: float = 12.0
    llm_max_tokens: int = 220
    llm_temperature: float = 0.2

    # --- orders ---
    orders_api_url: str = ""
    orders_api_token: str = ""
    orders_timeout_seconds: float = 5.0
    orders_fixture_path: str = "ml/data/orders.json"
    enable_mock_orders_api: bool = True

    # --- notifications ---
    slack_webhook_url: str = ""
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_username: str = ""
    smtp_password: str = ""
    smtp_from: str = ""
    handoff_email_to: str = ""

    # --- outbound ---
    outbound_mode: Literal["auto", "mock"] = "auto"
    sender_timeout_seconds: float = 10.0
    sender_max_retries: int = 3

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]

    @property
    def is_sqlite(self) -> bool:
        return self.database_url.startswith("sqlite")

    @property
    def portal_mock_connect_allowed(self) -> bool:
        return self.portal_allow_mock_channel_connect and self.environment != "production"

    @property
    def portal_secret(self) -> str:
        return self.portal_encryption_key or self.app_secret or "orbit-dev-portal-secret"

    @property
    def portal_meta_configured(self) -> bool:
        return bool(self.portal_meta_app_id and self.portal_meta_app_secret)

    @property
    def portal_oauth_redirect(self) -> str:
        return self.portal_oauth_redirect_uri or (f"{self.portal_public_url.rstrip('/')}/portal")

    def resolve_path(self, value: str) -> Path:
        path = Path(value)
        return path if path.is_absolute() else PROJECT_ROOT / path


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
