from __future__ import annotations

from datetime import timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import Conversation, Handoff, Message, PredictionLog, utcnow
from app.schemas import (
    ConfidenceBucket,
    DriftOut,
    IntentStat,
    OverviewOut,
    VolumePoint,
)
from app.security import require_admin
from shared.labels import (
    CONVERSATION_NEEDS_HUMAN,
    CONVERSATION_RESOLVED,
    HANDOFF_ASSIGNED,
    HANDOFF_OPEN,
    INTENTS,
)

router = APIRouter(
    prefix="/api/analytics",
    tags=["analytics"],
    dependencies=[Depends(require_admin)],
)

DRIFT_TVD_THRESHOLD = 0.20
DRIFT_CONFIDENCE_THRESHOLD = 0.10
DRIFT_MIN_SAMPLES = 30


@router.get("/overview", response_model=OverviewOut)
def overview(
    days: Annotated[int, Query(ge=1, le=90)] = 7, db: Session = Depends(get_db)
) -> OverviewOut:
    since = utcnow() - timedelta(days=days)

    def count(query) -> int:
        return int(db.scalar(query) or 0)

    conversations = count(
        select(func.count(Conversation.id)).where(Conversation.created_at >= since)
    )
    active_conversations = count(
        select(func.count(Conversation.id)).where(
            Conversation.status.in_(["bot", CONVERSATION_NEEDS_HUMAN])
        )
    )
    needs_human = count(
        select(func.count(Conversation.id)).where(
            Conversation.status == CONVERSATION_NEEDS_HUMAN
        )
    )
    inbound = count(
        select(func.count(Message.id)).where(
            Message.direction == "inbound", Message.created_at >= since
        )
    )
    outbound = count(
        select(func.count(Message.id)).where(
            Message.direction == "outbound", Message.created_at >= since
        )
    )
    resolved = count(
        select(func.count(Conversation.id)).where(
            Conversation.status == CONVERSATION_RESOLVED,
            Conversation.updated_at >= since,
        )
    )
    handoffs = count(
        select(func.count(Handoff.id)).where(Handoff.created_at >= since)
    )
    open_handoffs = count(
        select(func.count(Handoff.id)).where(
            Handoff.status.in_([HANDOFF_OPEN, HANDOFF_ASSIGNED])
        )
    )
    avg_conf = db.scalar(
        select(func.avg(PredictionLog.confidence)).where(PredictionLog.created_at >= since)
    )

    from app.models import FeedbackRecord

    pending_feedback = count(
        select(func.count(FeedbackRecord.id)).where(FeedbackRecord.status == "pending")
    )

    return OverviewOut(
        days=days,
        conversations=conversations,
        active_conversations=active_conversations,
        needs_human=needs_human,
        inbound_messages=inbound,
        outbound_messages=outbound,
        bot_resolved=resolved,
        handoffs=handoffs,
        handoff_rate=round(handoffs / conversations, 4) if conversations else 0.0,
        resolution_rate=round(resolved / conversations, 4) if conversations else 0.0,
        avg_confidence=round(float(avg_conf), 4) if avg_conf is not None else None,
        open_handoffs=open_handoffs,
        pending_feedback=pending_feedback,
    )


@router.get("/intents", response_model=list[IntentStat])
def intent_stats(
    days: Annotated[int, Query(ge=1, le=90)] = 7, db: Session = Depends(get_db)
) -> list[IntentStat]:
    since = utcnow() - timedelta(days=days)
    rows = db.execute(
        select(
            PredictionLog.intent,
            func.count(PredictionLog.id),
            func.avg(PredictionLog.confidence),
        )
        .where(PredictionLog.created_at >= since)
        .group_by(PredictionLog.intent)
    ).all()
    counts = {row[0]: (int(row[1]), float(row[2]) if row[2] is not None else None) for row in rows}
    total = sum(value[0] for value in counts.values())
    output: list[IntentStat] = []
    for intent in INTENTS:
        count, avg = counts.get(intent, (0, None))
        output.append(
            IntentStat(
                intent=intent,
                count=count,
                share=round(count / total, 4) if total else 0.0,
                avg_confidence=round(avg, 4) if avg is not None else None,
            )
        )
    return output


@router.get("/confidence", response_model=list[ConfidenceBucket])
def confidence_histogram(
    days: Annotated[int, Query(ge=1, le=90)] = 7, db: Session = Depends(get_db)
) -> list[ConfidenceBucket]:
    since = utcnow() - timedelta(days=days)
    rows = db.scalars(
        select(PredictionLog.confidence).where(
            PredictionLog.created_at >= since, PredictionLog.confidence.is_not(None)
        )
    ).all()
    buckets = [0] * 10
    for value in rows:
        index = min(9, max(0, int(float(value) * 10)))
        buckets[index] += 1
    return [
        ConfidenceBucket(bucket=f"{index / 10:.1f}-{(index + 1) / 10:.1f}", count=count)
        for index, count in enumerate(buckets)
    ]


@router.get("/volume", response_model=list[VolumePoint])
def volume(
    days: Annotated[int, Query(ge=1, le=90)] = 14, db: Session = Depends(get_db)
) -> list[VolumePoint]:
    since = utcnow() - timedelta(days=days)
    date_col = func.date(Message.created_at)
    rows = db.execute(
        select(date_col, Message.direction, func.count(Message.id))
        .where(Message.created_at >= since)
        .group_by(date_col, Message.direction)
    ).all()
    by_date: dict[str, dict[str, int]] = {}
    for day, direction, count in rows:
        key = str(day)
        by_date.setdefault(key, {"inbound": 0, "outbound": 0})[direction] = int(count)

    output: list[VolumePoint] = []
    start = (utcnow() - timedelta(days=days - 1)).date()
    for offset in range(days):
        key = (start + timedelta(days=offset)).isoformat()
        values = by_date.get(key, {"inbound": 0, "outbound": 0})
        output.append(
            VolumePoint(date=key, inbound=values.get("inbound", 0), outbound=values.get("outbound", 0))
        )
    return output


def _distribution(values: list[tuple[str, float]]) -> tuple[dict[str, float], float | None]:
    counts = {intent: 0 for intent in INTENTS}
    confidence_total = 0.0
    for intent, confidence in values:
        counts[intent] = counts.get(intent, 0) + 1
        confidence_total += float(confidence or 0)
    total = len(values)
    if not total:
        return {intent: 0.0 for intent in INTENTS}, None
    distribution = {intent: count / total for intent, count in counts.items()}
    return distribution, confidence_total / total


@router.get("/drift", response_model=DriftOut)
def drift(db: Session = Depends(get_db)) -> DriftOut:
    now = utcnow()
    current_start = now - timedelta(days=7)
    previous_start = now - timedelta(days=14)

    current_rows = db.execute(
        select(PredictionLog.intent, PredictionLog.confidence).where(
            PredictionLog.created_at >= current_start
        )
    ).all()
    previous_rows = db.execute(
        select(PredictionLog.intent, PredictionLog.confidence).where(
            PredictionLog.created_at >= previous_start,
            PredictionLog.created_at < current_start,
        )
    ).all()

    current_dist, current_conf = _distribution([(row[0], row[1]) for row in current_rows])
    previous_dist, previous_conf = _distribution([(row[0], row[1]) for row in previous_rows])
    tvd = 0.5 * sum(abs(current_dist.get(intent, 0) - previous_dist.get(intent, 0)) for intent in INTENTS)
    confidence_delta = (
        (current_conf or 0.0) - (previous_conf or 0.0)
        if current_conf is not None and previous_conf is not None
        else 0.0
    )
    enough_data = len(current_rows) >= DRIFT_MIN_SAMPLES and len(previous_rows) >= DRIFT_MIN_SAMPLES
    flagged = bool(
        enough_data
        and (
            tvd >= DRIFT_TVD_THRESHOLD
            or abs(confidence_delta) >= DRIFT_CONFIDENCE_THRESHOLD
        )
    )
    intent_shift = {
        intent: round(current_dist.get(intent, 0) - previous_dist.get(intent, 0), 4)
        for intent in INTENTS
    }
    note = (
        "Not enough predictions to judge drift yet."
        if not enough_data
        else ("Drift threshold exceeded. Review recent predictions and retraining queue." if flagged else "No material drift detected.")
    )
    return DriftOut(
        flagged=flagged,
        current_window={
            "start": current_start.isoformat(),
            "end": now.isoformat(),
            "samples": len(current_rows),
            "avg_confidence": round(current_conf, 4) if current_conf is not None else None,
            "distribution": {key: round(value, 4) for key, value in current_dist.items()},
        },
        previous_window={
            "start": previous_start.isoformat(),
            "end": current_start.isoformat(),
            "samples": len(previous_rows),
            "avg_confidence": round(previous_conf, 4) if previous_conf is not None else None,
            "distribution": {key: round(value, 4) for key, value in previous_dist.items()},
        },
        total_variation=round(tvd, 4),
        confidence_delta=round(confidence_delta, 4),
        intent_shift=intent_shift,
        thresholds={
            "total_variation": DRIFT_TVD_THRESHOLD,
            "confidence_delta": DRIFT_CONFIDENCE_THRESHOLD,
            "min_samples": DRIFT_MIN_SAMPLES,
        },
        note=note,
    )
