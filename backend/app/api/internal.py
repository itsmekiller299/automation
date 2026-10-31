from __future__ import annotations

from fastapi import APIRouter, HTTPException

from app.config import settings
from app.services.orders import OrdersClient

router = APIRouter(prefix="/internal", tags=["internal"])


@router.get("/orders/{order_id}")
def mock_order(order_id: str) -> dict:
    """Tiny read-only orders service for local demos.

    Point ORDERS_API_URL at your real internal service in production and set
    ENABLE_MOCK_ORDERS_API=false.
    """
    if not settings.enable_mock_orders_api:
        raise HTTPException(status_code=404, detail="Not found")
    client = OrdersClient(base_url="")
    result = client.lookup(order_id)
    if not result.found or not result.order:
        raise HTTPException(status_code=404, detail="Order not found")
    return result.order
