"""
Events API — History log + event simulation for testing.
"""

from __future__ import annotations

import time
from typing import List, Optional

import structlog
from fastapi import APIRouter, Depends, Query
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.context_manager import global_context
from backend.core.event_bus import event_bus
from backend.database import get_db
from backend.events.models import CompetitionEvent, EventType, EVENT_SEVERITY
from backend.models import EventLog
from backend.schemas import EventLogResponse, EventSimulateRequest
from backend.websocket.manager import ws_manager

log = structlog.get_logger(__name__)
router = APIRouter()


@router.get("/", response_model=List[EventLogResponse])
async def list_events(
    limit: int = Query(100, le=500),
    event_type: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
):
    q = select(EventLog).order_by(desc(EventLog.received_at)).limit(limit)
    if event_type:
        q = q.where(EventLog.event_type == event_type)
    result = await db.execute(q)
    return result.scalars().all()


@router.post("/simulate", status_code=202)
async def simulate_event(payload: EventSimulateRequest):
    """
    Inject a synthetic event directly into the Event Bus.
    Used by the UI event simulator panel for rule testing.
    """
    try:
        event_type = EventType(payload.event_type.upper())
    except ValueError:
        event_type = EventType.UNKNOWN

    event = CompetitionEvent(
        type=event_type,
        severity=EVENT_SEVERITY.get(event_type),
        competition_id=payload.competition_id,
        athlete_id=payload.athlete_id,
        lane=payload.lane,
        raw_payload={"simulated": True, **(payload.extra or {})},
    )

    delivered = await event_bus.publish(event)
    global_context.mark_event_activity()
    await ws_manager.broadcast_event_received(event)
    log.info("events.simulated", event_type=event_type, delivered=delivered)

    return {"event_id": event.id, "delivered_to": delivered}


@router.get("/types")
async def list_event_types():
    """Return all known event types with their severity."""
    return [
        {"type": et.value, "severity": EVENT_SEVERITY.get(et, "MEDIUM")}
        for et in EventType
    ]
