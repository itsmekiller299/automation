from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db import get_db
from app.dialogue.session import session_store
from app.models import Conversation, Customer, Message, PredictionLog
from app.schemas import DeleteCustomerIn
from app.security import require_admin

router = APIRouter(
    prefix="/api/privacy",
    tags=["privacy"],
    dependencies=[Depends(require_admin)],
)


@router.post("/delete")
def delete_customer_data(
    body: DeleteCustomerIn, db: Session = Depends(get_db)
) -> dict:
    """Hard-delete a customer and every conversation/message we hold.

    Deletion is intentionally keyed by the channel's external ID or our
    customer ID. The caller must set confirm=true. Tokens live in environment
    secrets and are never present in these tables.
    """
    if body.customer_id:
        customer = db.get(Customer, body.customer_id)
    elif body.channel and body.external_id:
        customer = db.scalar(
            select(Customer).where(
                Customer.channel == body.channel,
                Customer.external_id == body.external_id,
            )
        )
    else:
        raise HTTPException(
            status_code=422,
            detail="Provide customer_id or both channel and external_id",
        )

    if not customer:
        raise HTTPException(status_code=404, detail="Customer not found")

    conversation_ids = list(
        db.scalars(select(Conversation.id).where(Conversation.customer_id == customer.id)).all()
    )
    message_count = int(
        db.scalar(
            select(func.count(Message.id)).where(Message.conversation_id.in_(conversation_ids))
        )
        or 0
    ) if conversation_ids else 0
    prediction_count = int(
        db.scalar(
            select(func.count(PredictionLog.id)).where(
                PredictionLog.conversation_id.in_(conversation_ids)
            )
        )
        or 0
    ) if conversation_ids else 0

    customer_id = customer.id
    db.delete(customer)
    db.commit()

    for conversation_id in conversation_ids:
        session_store.delete(conversation_id)

    return {
        "status": "deleted",
        "customer_id": customer_id,
        "deleted": {
            "customers": 1,
            "conversations": len(conversation_ids),
            "messages": message_count,
            "predictions": prediction_count,
        },
    }
