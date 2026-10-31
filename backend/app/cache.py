from __future__ import annotations

import json
import logging
import threading
import time
from typing import Any

from app.config import settings

logger = logging.getLogger(__name__)


class Cache:
    """Redis-backed cache with an in-process fallback.

    The fallback keeps local development and the test suite working without a
    Redis server. In production set REDIS_URL and run Redis; sessions and
    idempotency keys then survive worker restarts and are shared across workers.
    """

    def __init__(self, url: str) -> None:
        self.url = url
        self._client: Any = None
        self._checked = False
        self._lock = threading.Lock()
        self._memory: dict[str, tuple[float | None, str]] = {}

    def _redis(self) -> Any:
        if self._checked:
            return self._client
        with self._lock:
            if self._checked:
                return self._client
            self._checked = True
            if not self.url:
                return None
            try:
                import redis

                client = redis.Redis.from_url(
                    self.url,
                    decode_responses=True,
                    socket_connect_timeout=0.5,
                    socket_timeout=0.8,
                )
                client.ping()
                self._client = client
                logger.info("Redis cache connected")
            except Exception as exc:  # pragma: no cover - depends on environment
                logger.warning("Redis unavailable, using in-memory cache: %s", exc)
                self._client = None
            return self._client

    def _mem_get(self, key: str) -> str | None:
        entry = self._memory.get(key)
        if not entry:
            return None
        expires_at, value = entry
        if expires_at is not None and expires_at < time.time():
            self._memory.pop(key, None)
            return None
        return value

    def _mem_set(self, key: str, value: str, ttl: int | None) -> None:
        expires = time.time() + ttl if ttl else None
        self._memory[key] = (expires, value)

    def get(self, key: str) -> str | None:
        client = self._redis()
        if client is not None:
            try:
                return client.get(key)
            except Exception as exc:  # pragma: no cover
                logger.warning("Redis GET failed, falling back: %s", exc)
        return self._mem_get(key)

    def set(self, key: str, value: str, ttl: int | None = None) -> None:
        client = self._redis()
        if client is not None:
            try:
                client.set(key, value, ex=ttl)
                return
            except Exception as exc:  # pragma: no cover
                logger.warning("Redis SET failed, falling back: %s", exc)
        self._mem_set(key, value, ttl)

    def set_if_absent(self, key: str, value: str, ttl: int | None = None) -> bool:
        client = self._redis()
        if client is not None:
            try:
                return bool(client.set(key, value, ex=ttl, nx=True))
            except Exception as exc:  # pragma: no cover
                logger.warning("Redis SETNX failed, falling back: %s", exc)
        if self._mem_get(key) is not None:
            return False
        self._mem_set(key, value, ttl)
        return True

    def delete(self, key: str) -> None:
        client = self._redis()
        if client is not None:
            try:
                client.delete(key)
                return
            except Exception:  # pragma: no cover
                pass
        self._memory.pop(key, None)

    def get_json(self, key: str) -> dict | None:
        raw = self.get(key)
        if not raw:
            return None
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            return None

    def set_json(self, key: str, value: dict, ttl: int | None = None) -> None:
        self.set(key, json.dumps(value, default=str), ttl=ttl)


cache = Cache(settings.redis_url)
