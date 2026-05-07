"""
Realization Decision Engine — The brain of Subvision Studio.

Runs on a tight cycle (default 50ms) and:
  1. Aggregates all CameraContext scores from CameraSubscriberRegistry
  2. Selects the best candidate camera using the scoring model
  3. Enforces global cooldown and minimum display duration
  4. Handles FORCE_SWITCH priority escalation
  5. Triggers OBS scene switch and preview loading
  6. Broadcasts decision trace to WebSocket clients for real-time debug
  7. Updates GlobalContext with current program/preview state

Architecture inspired by Gabin's weight-based autocam loop, but event-driven
instead of audio-level driven.
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional, TYPE_CHECKING

import structlog

from backend.core.context_manager import GlobalContext, SwitchRecord, global_context
from backend.core.settings import get_settings
from backend.realization.camera_context import CameraContext, ReactionMode
from backend.realization.camera_subscriber import subscriber_registry

if TYPE_CHECKING:
    from backend.obs.client import OBSClient

log = structlog.get_logger(__name__)
settings = get_settings()


@dataclass
class DecisionTrace:
    """Full decision audit trail emitted to WebSocket every cycle."""
    cycle_at: float = field(default_factory=time.time)
    candidates: List[dict] = field(default_factory=list)
    winner: Optional[str] = None
    winner_score: float = 0.0
    winner_reason: str = ""
    switch_triggered: bool = False
    blocked_reason: Optional[str] = None
    global_cooldown_active: bool = False
    min_display_enforced: bool = False

    def to_dict(self) -> dict:
        return {
            "cycle_at": self.cycle_at,
            "candidates": self.candidates,
            "winner": self.winner,
            "winner_score": round(self.winner_score, 2),
            "winner_reason": self.winner_reason,
            "switch_triggered": self.switch_triggered,
            "blocked_reason": self.blocked_reason,
            "global_cooldown_active": self.global_cooldown_active,
            "min_display_enforced": self.min_display_enforced,
        }


class RealizationDecisionEngine:
    """
    Core decision loop: evaluate all camera scores, pick the winner,
    execute the switch.
    """

    def __init__(self, obs_client: Optional["OBSClient"] = None) -> None:
        self._obs = obs_client
        self._ctx = global_context
        self._ws_broadcast_cb = None  # set by WebSocket manager at startup
        
        # Engine parameters (defaults from settings, can be overridden by active profile)
        self._cycle_interval = settings.decision_cycle_ms / 1000.0
        self._min_display_ms = settings.min_display_duration_ms
        self._score_threshold = settings.score_threshold_switch
        self._default_cooldown_ms = settings.default_cooldown_ms

    def set_obs_client(self, client: "OBSClient") -> None:
        self._obs = client

    def set_ws_broadcast(self, callback) -> None:
        """Register a callback to broadcast decision traces via WebSocket."""
        self._ws_broadcast_cb = callback

    async def _sync_profile(self) -> None:
        from sqlalchemy import select
        from backend.database import AsyncSessionLocal
        from backend.models import RuleProfile
        
        async with AsyncSessionLocal() as session:
            result = await session.execute(select(RuleProfile).where(RuleProfile.is_active == True))
            active_profile = result.scalars().first()
            
        if active_profile and active_profile.config:
            config = active_profile.config
            if "decision_cycle_ms" in config:
                self._cycle_interval = config["decision_cycle_ms"] / 1000.0
            if "min_display_duration_ms" in config:
                self._min_display_ms = config["min_display_duration_ms"]
            if "score_threshold_switch" in config:
                self._score_threshold = config["score_threshold_switch"]
            if "default_cooldown_ms" in config:
                self._default_cooldown_ms = config["default_cooldown_ms"]
        else:
            # Revert to settings defaults
            self._cycle_interval = settings.decision_cycle_ms / 1000.0
            self._min_display_ms = settings.min_display_duration_ms
            self._score_threshold = settings.score_threshold_switch
            self._default_cooldown_ms = settings.default_cooldown_ms

    async def run(self) -> None:
        log.info("decision_engine.started", cycle_ms=settings.decision_cycle_ms)
        cycle_count = 0
        try:
            while True:
                if cycle_count % 20 == 0:  # Sync profile every ~1 second (assuming 50ms cycle)
                    await self._sync_profile()
                cycle_count += 1
                
                cycle_start = time.monotonic()
                trace = await self._evaluate_cycle()

                # Broadcast trace to all WebSocket clients
                if self._ws_broadcast_cb and trace:
                    asyncio.create_task(
                        self._ws_broadcast_cb({"type": "decision_trace", "data": trace.to_dict()})
                    )

                elapsed = time.monotonic() - cycle_start
                sleep = max(0.0, self._cycle_interval - elapsed)
                await asyncio.sleep(sleep)

        except asyncio.CancelledError:
            log.info("decision_engine.cancelled")

    async def _evaluate_cycle(self) -> DecisionTrace:
        trace = DecisionTrace()
        contexts = subscriber_registry.get_all_contexts()

        if not contexts:
            return trace

        # ── 1. Build candidate list ────────────────────────────────────
        candidates = []
        force_candidates = []

        for ctx in contexts:
            score_dict = ctx.raw_score_components or {}
            pending_mode = ctx.pending_mode

            candidate = {
                "camera_id": ctx.camera_id,
                "score": ctx.interest_score,
                "mode": pending_mode,
                "pending": ctx.pending_transition,
                "in_cooldown": ctx.is_in_cooldown,
                "on_air": ctx.is_on_air,
                **score_dict,
            }
            candidates.append(candidate)

            if (
                ctx.pending_transition
                and pending_mode == ReactionMode.FORCE_SWITCH
                and not ctx.is_in_cooldown
            ):
                force_candidates.append(ctx)

        trace.candidates = candidates

        # ── 2. Check global cooldown ───────────────────────────────────
        if self._ctx.is_global_cooldown_active:
            trace.global_cooldown_active = True
            trace.blocked_reason = "global_cooldown_active"
            # Exception: FORCE_SWITCH ignores global cooldown
            if not force_candidates:
                return trace

        # ── 3. Enforce minimum display duration ────────────────────────
        time_on_air_ms = self._ctx.time_on_current_camera_ms
        if time_on_air_ms < self._min_display_ms and not force_candidates:
            trace.min_display_enforced = True
            trace.blocked_reason = f"min_display_not_reached ({time_on_air_ms:.0f}ms < {self._min_display_ms}ms)"
            return trace

        # ── 4. Elect winner ────────────────────────────────────────────
        winner_ctx: Optional[CameraContext] = None

        # FORCE_SWITCH wins unconditionally (highest priority among force candidates)
        if force_candidates:
            winner_ctx = max(force_candidates, key=lambda c: c.interest_score)
            trace.winner_reason = "FORCE_SWITCH"
        else:
            # Pick highest-scored camera with a pending switch signal above threshold
            eligible = [
                ctx for ctx in contexts
                if ctx.pending_transition
                and ctx.pending_mode in (ReactionMode.SWITCH_IF_HIGH_SCORE, ReactionMode.FORCE_SWITCH)
                and not ctx.is_in_cooldown
                and ctx.interest_score >= self._score_threshold
                and ctx.camera_id != self._ctx.program_camera_id  # don't re-switch to same cam
            ]
            if eligible:
                winner_ctx = max(eligible, key=lambda c: c.interest_score)
                trace.winner_reason = f"SWITCH_IF_HIGH_SCORE (score={winner_ctx.interest_score:.1f})"

        if winner_ctx is None:
            # Also handle PREPARE mode: load preview without switching
            await self._handle_prepare_mode(contexts)
            return trace

        # ── 5. Execute switch ──────────────────────────────────────────
        trace.winner = winner_ctx.camera_id
        trace.winner_score = winner_ctx.interest_score
        trace.switch_triggered = True

        await self._execute_switch(winner_ctx, trace)
        return trace

    async def _execute_switch(self, winner: CameraContext, trace: DecisionTrace) -> None:
        prev_camera = self._ctx.program_camera_id
        now = time.monotonic()

        log.info(
            "decision_engine.switch",
            from_camera=prev_camera,
            to_camera=winner.camera_id,
            score=winner.interest_score,
            reason=trace.winner_reason,
        )

        # ── Update program state ───────────────────────────────────────
        if prev_camera:
            prev_ctx = subscriber_registry.get_subscriber(prev_camera)
            if prev_ctx:
                prev_ctx.context.mark_off_air()

        winner.mark_on_air()
        winner.pending_transition = False
        winner.pending_mode = None

        # Apply cooldown to winner (anti-zap)
        if self._default_cooldown_ms > 0:
            winner.set_cooldown(self._default_cooldown_ms)

        self._ctx.program_camera_id = winner.camera_id
        self._ctx.program_since = now

        # Apply global cooldown
        self._ctx.set_global_cooldown(self._default_cooldown_ms)

        # Record switch
        self._ctx.record_switch(SwitchRecord(
            from_camera=prev_camera,
            to_camera=winner.camera_id,
            reason=trace.winner_reason,
            score=winner.interest_score,
            event_type=winner.last_event_type,
        ))

        # ── OBS integration ────────────────────────────────────────────
        if self._obs and settings.obs_enabled:
            try:
                await self._obs.set_program_scene(winner.camera_id)
            except Exception as e:
                log.error("decision_engine.obs_switch_failed", error=str(e))

    async def _handle_prepare_mode(self, contexts: list[CameraContext]) -> None:
        """Load PREPARE-mode cameras into OBS preview without switching program."""
        prepare_candidates = [
            ctx for ctx in contexts
            if ctx.pending_transition and ctx.pending_mode == ReactionMode.PREPARE
        ]
        if prepare_candidates and self._obs and settings.obs_enabled:
            best = max(prepare_candidates, key=lambda c: c.interest_score)
            if best.camera_id != self._ctx.preview_camera_id:
                try:
                    await self._obs.set_preview_scene(best.camera_id)
                    self._ctx.preview_camera_id = best.camera_id
                    log.info("decision_engine.preview_preloaded", camera_id=best.camera_id)
                except Exception as e:
                    log.error("decision_engine.obs_preview_failed", error=str(e))


# ── Singleton ─────────────────────────────────────────────────────────────────
decision_engine = RealizationDecisionEngine()
