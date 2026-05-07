"""
Scoring Engine — Computes per-camera interest scores.

Formula (inspired by Gabin's mic weight system, adapted for event-driven context):

  score = event_priority
        + activity_weight        (decaying function of time since last event)
        + critical_bonus         (extra score for CRITICAL severity events)
        + long_wait_bonus        (bonus if camera hasn't been on air for a while)
        - cooldown_penalty       (heavy penalty if in cooldown)
        - repetition_penalty     (penalty for switching back to same camera quickly)
        - off_air_staleness      (small penalty if camera was never active)

All values are clamped to [0, 100].
"""

from __future__ import annotations

import math
import time
from dataclasses import dataclass
from typing import Optional

from backend.events.models import EventSeverity, SEVERITY_BASE_SCORE
from backend.realization.camera_context import CameraContext, CameraSubscription, ReactionMode


# ── Tuning constants ─────────────────────────────────────────────────────────
ACTIVITY_DECAY_HALF_LIFE_S = 3.0     # score halves every 3s without new events
CRITICAL_BONUS = 25.0
LONG_WAIT_BONUS_THRESHOLD_S = 30.0   # start adding bonus after 30s off-air
LONG_WAIT_MAX_BONUS = 15.0
COOLDOWN_PENALTY = 80.0              # effectively blocks switch during cooldown
REPETITION_WINDOW_S = 5.0           # penalty if was on-air within last 5s
REPETITION_PENALTY = 30.0
FORCE_SWITCH_SCORE = 999.0          # guarantees selection


@dataclass
class ScoreBreakdown:
    camera_id: str
    total_score: float
    event_priority: float = 0.0
    activity_weight: float = 0.0
    critical_bonus: float = 0.0
    long_wait_bonus: float = 0.0
    cooldown_penalty: float = 0.0
    repetition_penalty: float = 0.0
    reaction_mode: Optional[str] = None
    is_force_switch: bool = False

    def to_dict(self) -> dict:
        return {
            "camera_id": self.camera_id,
            "total_score": round(self.total_score, 2),
            "event_priority": round(self.event_priority, 2),
            "activity_weight": round(self.activity_weight, 2),
            "critical_bonus": round(self.critical_bonus, 2),
            "long_wait_bonus": round(self.long_wait_bonus, 2),
            "cooldown_penalty": round(self.cooldown_penalty, 2),
            "repetition_penalty": round(self.repetition_penalty, 2),
            "reaction_mode": self.reaction_mode,
            "is_force_switch": self.is_force_switch,
        }


def compute_score(
    context: CameraContext,
    subscription: Optional[CameraSubscription],
) -> ScoreBreakdown:
    """
    Compute interest score for a camera given its current context and
    the matched subscription (if any) for the triggering event.
    """
    now = time.monotonic()
    bd = ScoreBreakdown(camera_id=context.camera_id, total_score=0.0)

    if subscription is None:
        # Not subscribed to this event type → minimal base score from activity decay
        time_since = context.time_since_last_activity
        bd.activity_weight = _activity_decay(50.0, time_since)
        bd.total_score = bd.activity_weight
        return _finalize(bd, context, now)

    bd.reaction_mode = subscription.mode

    # ── FORCE_SWITCH: bypass all scoring ──────────────────────────────
    if subscription.mode == ReactionMode.FORCE_SWITCH and not context.is_in_cooldown:
        bd.is_force_switch = True
        bd.total_score = FORCE_SWITCH_SCORE
        return bd

    # ── Base event priority ───────────────────────────────────────────
    bd.event_priority = subscription.priority

    # ── Activity decay: more recent event → higher weight ────────────
    time_since = context.time_since_last_activity
    bd.activity_weight = _activity_decay(subscription.priority, time_since)

    # ── Critical severity bonus ───────────────────────────────────────
    if context.last_event_severity == EventSeverity.CRITICAL:
        bd.critical_bonus = CRITICAL_BONUS

    # ── Long-wait bonus: cameras starved from air get a nudge ─────────
    if context.time_since_last_on_air > LONG_WAIT_BONUS_THRESHOLD_S:
        ratio = min(1.0, (context.time_since_last_on_air - LONG_WAIT_BONUS_THRESHOLD_S) / 60.0)
        bd.long_wait_bonus = ratio * LONG_WAIT_MAX_BONUS

    return _finalize(bd, context, now)


def _finalize(bd: ScoreBreakdown, context: CameraContext, now: float) -> ScoreBreakdown:
    """Apply penalties and clamp."""

    # ── Cooldown penalty ──────────────────────────────────────────────
    if context.is_in_cooldown:
        bd.cooldown_penalty = COOLDOWN_PENALTY

    # ── Repetition penalty ────────────────────────────────────────────
    if context.is_on_air or (now - context.last_on_air_at) < REPETITION_WINDOW_S:
        bd.repetition_penalty = REPETITION_PENALTY

    raw = (
        bd.event_priority
        + bd.activity_weight
        + bd.critical_bonus
        + bd.long_wait_bonus
        - bd.cooldown_penalty
        - bd.repetition_penalty
    )

    bd.total_score = max(0.0, min(100.0, raw))
    return bd


def _activity_decay(base_score: float, time_since_s: float) -> float:
    """
    Exponential decay: score = base * 0.5^(t / half_life)
    Returns 0 if camera has been inactive for too long (>5x half-life).
    """
    if time_since_s > ACTIVITY_DECAY_HALF_LIFE_S * 5:
        return 0.0
    decay = math.pow(0.5, time_since_s / ACTIVITY_DECAY_HALF_LIFE_S)
    return base_score * decay
