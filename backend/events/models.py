"""
Competition Event Models — Pydantic v2

Defines all event types that can arrive from the external competition API.
Events are timestamped with both wall clock (UTC ISO) and monotonic clock
(for precise frame alignment in sub-100ms windows).
"""

from __future__ import annotations

import time
import uuid
from enum import Enum
from typing import Any, Dict, Optional

from pydantic import BaseModel, Field


class EventType(str, Enum):
    # Match lifecycle
    MATCH_START = "MATCH_START"
    MATCH_END = "MATCH_END"

    # Athlete
    ATHLETE_READY = "ATHLETE_READY"
    ATHLETE_POSITION = "ATHLETE_POSITION"

    # Shooting actions
    SHOT_FIRED = "SHOT_FIRED"
    ARROW_RECOVERY = "ARROW_RECOVERY"
    TARGET_VALIDATION = "TARGET_VALIDATION"

    # Officiating
    PENALTY = "PENALTY"
    TIMEOUT = "TIMEOUT"
    REFEREE_ANNOUNCEMENT = "REFEREE_ANNOUNCEMENT"

    # System
    SYSTEM_HEARTBEAT = "SYSTEM_HEARTBEAT"

    # Unknown (graceful handling of future event types)
    UNKNOWN = "UNKNOWN"


class EventSeverity(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


# Severity mapping used by the scoring engine
EVENT_SEVERITY: Dict[EventType, EventSeverity] = {
    EventType.SHOT_FIRED: EventSeverity.CRITICAL,
    EventType.MATCH_START: EventSeverity.HIGH,
    EventType.MATCH_END: EventSeverity.HIGH,
    EventType.TARGET_VALIDATION: EventSeverity.HIGH,
    EventType.PENALTY: EventSeverity.HIGH,
    EventType.ARROW_RECOVERY: EventSeverity.MEDIUM,
    EventType.ATHLETE_READY: EventSeverity.MEDIUM,
    EventType.TIMEOUT: EventSeverity.MEDIUM,
    EventType.REFEREE_ANNOUNCEMENT: EventSeverity.MEDIUM,
    EventType.ATHLETE_POSITION: EventSeverity.LOW,
    EventType.SYSTEM_HEARTBEAT: EventSeverity.LOW,
    EventType.UNKNOWN: EventSeverity.LOW,
}

# Base priority score by severity (used in scoring formula)
SEVERITY_BASE_SCORE: Dict[EventSeverity, float] = {
    EventSeverity.CRITICAL: 100.0,
    EventSeverity.HIGH: 70.0,
    EventSeverity.MEDIUM: 40.0,
    EventSeverity.LOW: 10.0,
}


class CompetitionEvent(BaseModel):
    """
    Canonical internal representation of a competition event.
    Produced by the Event Engine after polling + normalizing the external API.
    """

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    type: EventType
    severity: EventSeverity = EventSeverity.MEDIUM

    # Timing
    received_at: float = Field(default_factory=time.time)   # wall clock UTC epoch
    monotonic_at: float = Field(default_factory=time.monotonic)  # for frame alignment

    # Competition context
    competition_id: Optional[str] = None
    athlete_id: Optional[str] = None
    lane: Optional[int] = None

    # Raw payload from external API (preserved for debugging/logging)
    raw_payload: Dict[str, Any] = Field(default_factory=dict)

    # Frame correlation
    frame_id: Optional[int] = None           # nearest video frame number (set by ingest)
    frame_timestamp: Optional[float] = None  # timestamp of nearest frame

    # Deduplication
    external_id: Optional[str] = None  # ID from external API if provided

    @classmethod
    def from_external(cls, payload: Dict[str, Any]) -> "CompetitionEvent":
        """
        Normalize an arbitrary external API payload into a CompetitionEvent.
        Handles unknown event types gracefully.
        """
        raw_type = payload.get("type") or payload.get("event_type") or "UNKNOWN"
        try:
            event_type = EventType(raw_type.upper())
        except ValueError:
            event_type = EventType.UNKNOWN

        severity = EVENT_SEVERITY.get(event_type, EventSeverity.LOW)

        return cls(
            type=event_type,
            severity=severity,
            competition_id=payload.get("competition_id"),
            athlete_id=payload.get("athlete_id"),
            lane=payload.get("lane"),
            frame_id=payload.get("frame_id"),
            frame_timestamp=payload.get("frame_timestamp"),
            external_id=payload.get("id") or payload.get("event_id"),
            raw_payload=payload,
        )
