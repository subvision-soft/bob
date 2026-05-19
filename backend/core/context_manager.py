"""
Global Context Manager — Single source of truth for the realization system.

Maintains:
  - Per-camera contexts (via CameraSubscriberRegistry reference)
  - Competition state
  - Current program camera
  - Recent switch history
  - System health stats

Thread-safe via asyncio.Lock.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional

import structlog

log = structlog.get_logger(__name__)


class CompetitionState:
    IDLE = "IDLE"
    RUNNING = "RUNNING"
    PAUSED = "PAUSED"
    ENDED = "ENDED"


@dataclass
class SwitchRecord:
    """Immutable record of a camera switch decision."""
    from_camera: Optional[str]
    to_camera: str
    reason: str
    score: float
    event_type: Optional[str]
    timestamp: float = field(default_factory=time.monotonic)
    wall_time: float = field(default_factory=time.time)


@dataclass
class GlobalContext:
    """
    Shared context for the entire Subvision Studio runtime.
    One instance lives for the duration of the application.
    """

    # ── Competition ───────────────────────────────────────────────────
    competition_state: str = CompetitionState.IDLE
    competition_id: Optional[str] = None

    # ── Program output ────────────────────────────────────────────────
    program_camera_id: Optional[str] = None      # Currently on air
    preview_camera_id: Optional[str] = None      # Loaded in preview
    program_since: float = 0.0
    program_scene_name: Optional[str] = None
    program_scene_since: float = 0.0

    # ── Timing ────────────────────────────────────────────────────────
    last_switch_at: float = 0.0
    last_event_at: float = 0.0

    # ── Switch history (last 50) ──────────────────────────────────────
    switch_history: List[SwitchRecord] = field(default_factory=list)
    MAX_HISTORY = 50

    # ── Global cooldown ───────────────────────────────────────────────
    global_cooldown_until: float = 0.0

    # ── Statistics ────────────────────────────────────────────────────
    total_switches: int = 0
    events_processed: int = 0

    def record_switch(self, record: SwitchRecord) -> None:
        self.switch_history.append(record)
        if len(self.switch_history) > self.MAX_HISTORY:
            self.switch_history.pop(0)
        self.total_switches += 1
        self.last_switch_at = time.monotonic()

    def mark_event_activity(self) -> None:
        self.events_processed += 1
        self.last_event_at = time.monotonic()

    @property
    def is_global_cooldown_active(self) -> bool:
        return time.monotonic() < self.global_cooldown_until

    def set_global_cooldown(self, ms: int) -> None:
        self.global_cooldown_until = time.monotonic() + ms / 1000.0

    @property
    def time_on_current_camera_ms(self) -> float:
        if self.program_since == 0.0:
            return 0.0
        return (time.monotonic() - self.program_since) * 1000.0

    def to_dict(self) -> dict:
        return {
            "competition_state": self.competition_state,
            "competition_id": self.competition_id,
            "program_camera_id": self.program_camera_id,
            "preview_camera_id": self.preview_camera_id,
            "program_scene_name": self.program_scene_name,
            "program_scene_since_ms": round(
                (time.monotonic() - self.program_scene_since) * 1000, 0
            ) if self.program_scene_since else 0,
            "time_on_current_camera_ms": round(self.time_on_current_camera_ms, 0),
            "is_global_cooldown_active": self.is_global_cooldown_active,
            "total_switches": self.total_switches,
            "events_processed": self.events_processed,
            "last_switch_reason": (
                self.switch_history[-1].reason if self.switch_history else None
            ),
        }


# ── Singleton ─────────────────────────────────────────────────────────────────
global_context = GlobalContext()
