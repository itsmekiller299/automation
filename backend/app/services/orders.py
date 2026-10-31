from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from urllib.parse import quote

import httpx

from app.config import settings
from app.nlu.entities import normalize_order_id

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class OrderLookup:
    found: bool
    order: dict | None = None
    source: str = "orders_api"
    error: str | None = None


class OrdersClient:
    """Internal orders API client with a read-only fixture fallback for demos.

    The bot only ever calls read endpoints. Refunds, cancellations, and address
    changes are handed to a human; this client cannot mutate an order.
    """

    def __init__(
        self,
        base_url: str | None = None,
        token: str | None = None,
        fixture_path: Path | None = None,
        timeout: float | None = None,
    ) -> None:
        self.base_url = (base_url if base_url is not None else settings.orders_api_url).rstrip("/")
        self.token = token if token is not None else settings.orders_api_token
        self.fixture_path = fixture_path or settings.resolve_path(settings.orders_fixture_path)
        self.timeout = timeout or settings.orders_timeout_seconds
        self._fixtures: dict | None = None

    def _load_fixtures(self) -> dict:
        if self._fixtures is not None:
            return self._fixtures
        try:
            self._fixtures = json.loads(self.fixture_path.read_text())
        except (FileNotFoundError, json.JSONDecodeError) as exc:
            logger.error("Could not load order fixtures: %s", exc)
            self._fixtures = {}
        return self._fixtures

    def _fixture_lookup(self, order_id: str) -> OrderLookup:
        normalized = normalize_order_id(order_id)
        order = self._load_fixtures().get(normalized)
        if not order:
            return OrderLookup(False, source="fixture", error="not_found")
        return OrderLookup(True, order=order, source="fixture")

    def lookup(self, order_id: str) -> OrderLookup:
        normalized = normalize_order_id(order_id)
        if not normalized:
            return OrderLookup(False, source="orders_api", error="invalid_order_id")
        if not self.base_url:
            return self._fixture_lookup(normalized)

        url = f"{self.base_url}/orders/{quote(normalized)}"
        headers = {"Accept": "application/json"}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        try:
            with httpx.Client(timeout=self.timeout) as client:
                response = client.get(url, headers=headers)
            if response.status_code == 404:
                return OrderLookup(False, source="orders_api", error="not_found")
            if response.status_code >= 400:
                logger.error("Orders API returned %s for %s", response.status_code, normalized)
                return OrderLookup(False, source="orders_api", error="upstream_error")
            data = response.json()
            return OrderLookup(True, order=data, source="orders_api")
        except (httpx.HTTPError, ValueError) as exc:
            logger.error("Orders API unavailable for %s: %s", normalized, exc)
            return OrderLookup(False, source="orders_api", error="unavailable")


@lru_cache
def get_orders_client() -> OrdersClient:
    return OrdersClient()
