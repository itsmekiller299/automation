from __future__ import annotations

from dataclasses import asdict, dataclass, fields

from app.cache import cache
from app.config import settings


@dataclass
class SessionState:
    last_intent: str | None = None
    pending_slot: str | None = None
    pending_attempts: int = 0
    fallback_count: int = 0
    non_text_count: int = 0
    bot_identified: bool = False
    turn_count: int = 0
    last_order_id: str | None = None
    last_updated: str | None = None

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, payload: dict | None) -> SessionState:
        if not payload:
            return cls()
        allowed = {field.name for field in fields(cls)}
        return cls(**{key: value for key, value in payload.items() if key in allowed})

    def reset_pending(self) -> None:
        self.pending_slot = None
        self.pending_attempts = 0


class SessionStore:
    def __init__(self) -> None:
        self.ttl = settings.session_ttl_seconds

    @staticmethod
    def _key(conversation_id: str) -> str:
        return f"session:{conversation_id}"

    def get(self, conversation_id: str) -> SessionState:
        return SessionState.from_dict(cache.get_json(self._key(conversation_id)))

    def save(self, conversation_id: str, state: SessionState) -> None:
        cache.set_json(self._key(conversation_id), state.to_dict(), ttl=self.ttl)

    def delete(self, conversation_id: str) -> None:
        cache.delete(self._key(conversation_id))


session_store = SessionStore()
