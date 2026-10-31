from __future__ import annotations

import json
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import PlainTextResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import FeedbackRecord, Message, PredictionLog
from app.schemas import FeedbackIn
from app.security import require_admin
from shared.labels import INTENTS

router = APIRouter(
    prefix="/api",
    tags=["feedback"],
    dependencies=[Depends(require_admin)],
)


@router.post("/predictions/{prediction_id}/feedback")
def correct_prediction(
    prediction_id: str,
    body: FeedbackIn,
    db: Session = Depends(get_db),
) -> dict:
    prediction = db.get(PredictionLog, prediction_id)
    if not prediction:
        raise HTTPException(status_code=404, detail="Prediction not found")
    if prediction.corrected_intent == body.corrected_intent:
        existing = db.scalar(
            select(FeedbackRecord).where(FeedbackRecord.prediction_id == prediction.id)
        )
        return {
            "status": "unchanged",
            "feedback_id": existing.id if existing else None,
            "corrected_intent": body.corrected_intent,
        }

    prediction.corrected_intent = body.corrected_intent
    message = db.get(Message, prediction.message_id) if prediction.message_id else None
    record = db.scalar(
        select(FeedbackRecord).where(FeedbackRecord.prediction_id == prediction.id)
    )
    if record:
        record.corrected_intent = body.corrected_intent
        record.agent = body.agent or record.agent
        record.status = "pending"
    else:
        record = FeedbackRecord(
            prediction_id=prediction.id,
            message_id=prediction.message_id,
            utterance=message.text if message else "",
            predicted_intent=prediction.intent,
            corrected_intent=body.corrected_intent,
            agent=body.agent,
            status="pending",
        )
        db.add(record)
    db.commit()
    return {
        "status": "queued_for_retraining",
        "feedback_id": record.id,
        "predicted_intent": prediction.intent,
        "corrected_intent": body.corrected_intent,
    }


@router.post("/messages/{message_id}/feedback")
def correct_message_prediction(
    message_id: str,
    body: FeedbackIn,
    db: Session = Depends(get_db),
) -> dict:
    """Correct the latest prediction for a message.

    The dashboard works from message IDs, so it should not need to know about
    internal prediction IDs. The underlying correction still flows through the
    same audited PredictionLog/FeedbackRecord path.
    """
    prediction = db.scalar(
        select(PredictionLog)
        .where(PredictionLog.message_id == message_id)
        .order_by(PredictionLog.created_at.desc())
        .limit(1)
    )
    if not prediction:
        raise HTTPException(status_code=404, detail="Prediction not found for message")
    return correct_prediction(prediction.id, body, db)


@router.get("/feedback")
def list_feedback(
    status_filter: Annotated[str | None, Query(alias="status")] = "pending",
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
    db: Session = Depends(get_db),
) -> dict:
    query = select(FeedbackRecord).order_by(FeedbackRecord.created_at.desc()).limit(limit)
    if status_filter:
        query = query.where(FeedbackRecord.status == status_filter)
    records = db.scalars(query).all()
    return {
        "items": [
            {
                "id": record.id,
                "prediction_id": record.prediction_id,
                "message_id": record.message_id,
                "utterance": record.utterance,
                "predicted_intent": record.predicted_intent,
                "corrected_intent": record.corrected_intent,
                "agent": record.agent,
                "status": record.status,
                "created_at": record.created_at.isoformat(),
            }
            for record in records
        ],
        "intents": INTENTS,
    }


@router.get("/feedback/export", response_class=PlainTextResponse)
def export_feedback(db: Session = Depends(get_db)) -> PlainTextResponse:
    """Export pending corrections as JSONL for the next training run."""
    records = db.scalars(
        select(FeedbackRecord)
        .where(FeedbackRecord.status == "pending")
        .order_by(FeedbackRecord.created_at)
    ).all()
    lines = [
        json.dumps(
            {
                "text": record.utterance,
                "intent": record.corrected_intent,
                "source": "agent_feedback",
                "predicted_intent": record.predicted_intent,
                "feedback_id": record.id,
            },
            ensure_ascii=False,
        )
        for record in records
        if record.utterance.strip()
    ]
    return PlainTextResponse(
        "\n".join(lines),
        media_type="application/x-ndjson",
        headers={"Content-Disposition": "attachment; filename=retraining-queue.jsonl"},
    )


@router.post("/feedback/{feedback_id}/mark-exported")
def mark_exported(feedback_id: str, db: Session = Depends(get_db)) -> dict:
    record = db.get(FeedbackRecord, feedback_id)
    if not record:
        raise HTTPException(status_code=404, detail="Feedback record not found")
    record.status = "exported"
    db.commit()
    return {"status": "exported", "id": record.id}
