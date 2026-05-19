"""
Camera Context — Per-camera mutable state maintained by CameraEventSubscriber.

This is the core data structure that drives the Realization Decision Engine.
Each camera maintains independent state that is continuously updated by its
subscriber, even when the camera is NOT currently on air.

This proactive (vs. reactive) design is what allows the system to anticipate
switches and prepare transitions before they happen.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import List, Optional

from backend.events.models import CompetitionEvent, EventSeverity


class ReactionMode(str, Enum):
    """
    Defines how a camera reacts to a matched event subscription.
    Maps directly to the INFORM_ONLY / PREPARE / SWITCH_IF_HIGH_SCORE / FORCE_SWITCH spec.
    """
    INFORM_ONLY = "INFORM_ONLY"         # Update context only, no switch
    PREPARE = "PREPARE"                 # Prewarm preview/PTZ, no immediate switch
    SWITCH_IF_HIGH_SCORE = "SWITCH_IF_HIGH_SCORE"  # Switch if score >= threshold
    FORCE_SWITCH = "FORCE_SWITCH"       # Absolute priority, immediate switch


@dataclass
class CameraSubscription:
    """One subscription entry in a camera's subscription list."""
    event_type: str                         # EventType string value
    mode: ReactionMode = ReactionMode.INFORM_ONLY
    priority: float = 50.0                  # 0-100
    duration_ms: int = 3000                 # min display duration after switch
    cooldown_ms: int = 0                    # per-subscription cooldown override
    delay_ms: int = 0                       # delay before triggering action
    enabled: bool = True
    conditions: dict = field(default_factory=dict)  # future: condition expressions
    obs_scene_options: List["ObsSceneOption"] = field(default_factory=list)


@dataclass
class ObsSceneOption:
    scene_name: str
    weight: float = 1.0
    max_display_ms: int = 0


@dataclass
class CameraContext:
    """
    Live state for one camera. Updated by CameraEventSubscriber.
    Read by the Realization Decision Engine.
    """
    camera_id: str
    source_type: Optional[str] = None
    obs_scene_name: Optional[str] = None
    obs_scene_weight: float = 1.0
    obs_scene_max_display_ms: int = 0

    # ── Event state ───────────────────────────────────────────────────
    last_event: Optional[CompetitionEvent] = None
    last_event_type: Optional[str] = None
    last_event_severity: Optional[EventSeverity] = None
    last_activity_at: float = field(default_factory=time.monotonic)

    # ── Scoring ───────────────────────────────────────────────────────
    interest_score: float = 0.0
    raw_score_components: dict = field(default_factory=dict)

    # ── Cooldown ──────────────────────────────────────────────────────
    cooldown_until: float = 0.0     # monotonic timestamp until which switch is suppressed
    global_cooldown_until: float = 0.0

    # ── Transition ───────────────────────────────────────────────────
    pending_transition: bool = False
    pending_mode: Optional[ReactionMode] = None
    pending_since: float = 0.0
    pending_event_type: Optional[str] = None

    # ── Air time tracking ────────────────────────────────────────────
    is_on_air: bool = False
    last_on_air_at: float = 0.0
    total_on_air_ms: float = 0.0

    # ── History (short-term) ─────────────────────────────────────────
    recent_events: List[str] = field(default_factory=list)  # last N event types
    switch_count: int = 0

    # ── Subscriptions ────────────────────────────────────────────────
    subscriptions: List[CameraSubscription] = field(default_factory=list)


    @property
    def is_in_cooldown(self) -> bool:
        return time.monotonic() < self.cooldown_until

    @property
    def time_since_last_activity(self) -> float:
        """Seconds since last event activity."""
        return time.monotonic() - self.last_activity_at

    @property
    def time_since_last_on_air(self) -> float:
        """Seconds since this camera was last on air."""
        if self.last_on_air_at == 0.0:
            return float("inf")
        return time.monotonic() - self.last_on_air_at

    def get_subscription(self, event_type: str) -> Optional[CameraSubscription]:
        """Return the subscription for a given event type, or None if not subscribed."""
        for sub in self.subscriptions:
            if sub.event_type == event_type and sub.enabled:
                return sub
        return None

    def set_cooldown(self, cooldown_ms: int) -> None:
        """Apply a cooldown period (in ms) from now."""
        if cooldown_ms > 0:
            self.cooldown_until = time.monotonic() + (cooldown_ms / 1000.0)

    def mark_on_air(self) -> None:
        self.is_on_air = True
        self.last_on_air_at = time.monotonic()
        self.switch_count += 1

    def mark_off_air(self) -> None:
        if self.is_on_air:
            elapsed_ms = (time.monotonic() - self.last_on_air_at) * 1000
            self.total_on_air_ms += elapsed_ms
        self.is_on_air = False

    def push_event(self, event: CompetitionEvent) -> None:
        """Record a received event into history."""
        self.last_event = event
        self.last_event_type = event.type
        self.last_event_severity = event.severity
        self.last_activity_at = time.monotonic()
        # Keep rolling window of last 10 event types
        self.recent_events.append(event.type)
        if len(self.recent_events) > 10:
            self.recent_events.pop(0)

    def to_dict(self) -> dict:
        """Serializable snapshot for WebSocket broadcast."""
        ts_last_on_air = self.time_since_last_on_air
        # JSON does not support Infinity. Use -1 to indicate "never".
        ts_last_on_air_val = round(ts_last_on_air, 2) if ts_last_on_air != float("inf") else -1

        return {
            "camera_id": self.camera_id,
            "last_event_type": self.last_event_type,
            "last_event_severity": self.last_event_severity,
            "interest_score": round(self.interest_score, 2),
            "is_on_air": self.is_on_air,
            "is_in_cooldown": self.is_in_cooldown,
            "cooldown_remaining_ms": max(0, (self.cooldown_until - time.monotonic()) * 1000),
            "pending_transition": self.pending_transition,
            "pending_mode": self.pending_mode,
            "time_since_last_activity_s": round(self.time_since_last_activity, 2),
            "time_since_last_on_air_s": ts_last_on_air_val,
            "switch_count": self.switch_count,
            "recent_events": self.recent_events[-5:],
        }
