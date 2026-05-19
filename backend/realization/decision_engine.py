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
import random
import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional, TYPE_CHECKING

import structlog

from backend.core.context_manager import GlobalContext, SwitchRecord, global_context
from backend.core.camera_registry import camera_registry
from backend.core.settings import get_settings
from backend.realization.camera_context import CameraContext, ReactionMode
from backend.models import Camera
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
    idle_rotation_triggered: bool = False
    scene_max_display_triggered: bool = False
    rotated_scene: Optional[str] = None
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
            "idle_rotation_triggered": self.idle_rotation_triggered,
            "scene_max_display_triggered": self.scene_max_display_triggered,
            "rotated_scene": self.rotated_scene,
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
        self._idle_scene_rotation_ms = settings.idle_scene_rotation_ms

    def set_obs_client(self, client: "OBSClient") -> None:
        self._obs = client

    def set_ws_broadcast(self, callback) -> None:
        """Register a callback to broadcast decision traces via WebSocket."""
        self._ws_broadcast_cb = callback

    async def _broadcast_state(self) -> None:
        if not self._ws_broadcast_cb:
            return
        try:
            await self._ws_broadcast_cb({"type": "global_context", "data": self._ctx.to_dict()})
            camera_scores = [ctx.to_dict() for ctx in subscriber_registry.get_all_contexts()]
            await self._ws_broadcast_cb({
                "type": "camera_scores",
                "data": camera_scores,
                "ts": time.time(),
            })
        except Exception:
            log.exception("decision_engine.broadcast_state_failed")

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
            if "idle_scene_rotation_ms" in config:
                self._idle_scene_rotation_ms = config["idle_scene_rotation_ms"]
        else:
            # Revert to settings defaults
            self._cycle_interval = settings.decision_cycle_ms / 1000.0
            self._min_display_ms = settings.min_display_duration_ms
            self._score_threshold = settings.score_threshold_switch
            self._default_cooldown_ms = settings.default_cooldown_ms
            self._idle_scene_rotation_ms = settings.idle_scene_rotation_ms

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
                if cycle_count % 200 == 0:
                    log.debug(
                        "decision_engine.cycle",
                        cycle=cycle_count,
                        elapsed_ms=round(elapsed * 1000.0, 2),
                        sleep_ms=round(sleep * 1000.0, 2),
                    )
                await asyncio.sleep(sleep)

        except asyncio.CancelledError:
            log.info("decision_engine.cancelled")
            raise
        except Exception:
            log.exception("decision_engine.failed")
            raise

    async def _evaluate_cycle(self) -> DecisionTrace:
        trace = DecisionTrace()
        contexts = subscriber_registry.get_all_contexts()
        cameras = camera_registry.get_all()

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


        # ── 2. Enforce hard max display rotations (ignores cooldowns) ─────────
        if await self._handle_obs_scene_camera_rotation(contexts, trace):
            return trace
        if await self._handle_scene_max_display(contexts, trace,cameras):
            return trace

        # ── 3. Check global cooldown ───────────────────────────────────
        if self._ctx.is_global_cooldown_active:
            trace.global_cooldown_active = True
            trace.blocked_reason = "global_cooldown_active"
            # Exception: FORCE_SWITCH ignores global cooldown
            if not force_candidates:
                return trace

        # ── 4. Enforce minimum display duration ────────────────────────
        time_on_air_ms = self._ctx.time_on_current_camera_ms
        if time_on_air_ms < self._min_display_ms and not force_candidates:
            trace.min_display_enforced = True
            trace.blocked_reason = f"min_display_not_reached ({time_on_air_ms:.0f}ms < {self._min_display_ms}ms)"
            return trace

        # ── 5. Elect winner ────────────────────────────────────────────
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
            if await self._handle_idle_rotation(cameras, trace):
                return trace
            return trace

        # ── 6. Execute switch ──────────────────────────────────────────
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
            scene_name = self._pick_obs_scene(winner)
            if scene_name is None:
                log.info(
                    "decision_engine.obs_switch_skipped",
                    camera_id=winner.camera_id,
                    reason="no_scene_options",
                )
            else:
                try:
                    await self._obs.set_program_scene(scene_name)
                    self._ctx.program_scene_name = scene_name
                    self._ctx.program_scene_since = time.monotonic()
                except Exception as e:
                    log.error("decision_engine.obs_switch_failed", error=str(e))

        await self._broadcast_state()

        # Clear pending transition fields after scene selection/execution
        winner.pending_transition = False
        winner.pending_mode = None
        winner.pending_event_type = None

    async def _handle_prepare_mode(self, contexts: list[CameraContext]) -> None:
        """Load PREPARE-mode cameras into OBS preview without switching program."""
        prepare_candidates = [
            ctx for ctx in contexts
            if ctx.pending_transition and ctx.pending_mode == ReactionMode.PREPARE
        ]
        if prepare_candidates and self._obs and settings.obs_enabled:
            best = max(prepare_candidates, key=lambda c: c.interest_score)
            if best.camera_id != self._ctx.preview_camera_id:
                scene_name = self._pick_obs_scene(best)
                if scene_name is None:
                    log.info(
                        "decision_engine.obs_preview_skipped",
                        camera_id=best.camera_id,
                        reason="no_scene_options",
                    )
                else:
                    try:
                        await self._obs.set_preview_scene(scene_name)
                        self._ctx.preview_camera_id = best.camera_id
                        log.info("decision_engine.preview_preloaded", camera_id=best.camera_id)
                        await self._broadcast_state()
                    except Exception as e:
                        log.error("decision_engine.obs_preview_failed", error=str(e))

    async def _handle_idle_rotation(self, cameras: list[Camera], trace: DecisionTrace) -> bool:
        """Rotate the current program camera's configured scenes after an idle period."""
        if not self._obs or not settings.obs_enabled:
            return False
        if self._idle_scene_rotation_ms <= 0:
            return False
        if not self._ctx.program_camera_id:
            return False

        idle_anchor_at = max(self._ctx.last_event_at, self._ctx.last_switch_at, self._ctx.program_since)
        if idle_anchor_at == 0.0:
            return False

        idle_ms = (time.monotonic() - idle_anchor_at) * 1000.0
        if idle_ms < self._idle_scene_rotation_ms:
            return False

        current_camera = next((cam for cam in cameras if cam.id == self._ctx.program_camera_id), None)
        if current_camera is None:
            return False

        if len(cameras) < 2:
            return False

        current_scene = self._obs.current_program_scene
        if not current_scene:
            return False
        next_scene = self._pick_weighted_scene(cameras, current_scene)
        if next_scene is None or next_scene == current_scene:
            return False

        try:
            await self._obs.set_program_scene(next_scene)
            self._ctx.program_scene_name = next_scene
            self._ctx.program_scene_since = time.monotonic()
            trace.switch_triggered = True
            trace.idle_rotation_triggered = True
            trace.rotated_scene = next_scene
            trace.winner = current_camera.id
            trace.winner_reason = f"IDLE_SCENE_ROTATION ({idle_ms:.0f}ms idle)"

            self._ctx.record_switch(SwitchRecord(
                from_camera=current_camera.id,
                to_camera=current_camera.id,
                reason=trace.winner_reason,
                score=100.0,  # full score for idle rotation
                event_type=None,
            ))

            log.info(
                "decision_engine.idle_scene_rotated",
                camera_id=current_camera.id,
                scene=next_scene,
                idle_ms=round(idle_ms, 0),
            )
            return True
        except Exception as e:
            log.error("decision_engine.idle_rotation_failed", error=str(e))
            return False

    async def _handle_scene_max_display(self, contexts: list[CameraContext], trace: DecisionTrace, cameras: List[Camera]) -> bool:
        """Rotate scenes when the current scene hits its max display time."""
        if not self._obs or not settings.obs_enabled:
            return False


        if not self._ctx.program_camera_id:
            return False

        current_scene = self._obs.current_program_scene
        if not current_scene:
            return False

        if self._ctx.program_scene_name != current_scene:
            self._ctx.program_scene_name = current_scene
            self._ctx.program_scene_since = time.monotonic()

        current_ctx = next((ctx for ctx in contexts if ctx.camera_id == self._ctx.program_camera_id), None)
        if current_ctx is None:
            return False

        if len(cameras) < 2:
            return False

        current_option = next((o for o in cameras if o.source_url == current_scene), None)
        if not current_option or current_option.obs_scene_max_display_ms <= 0:
            return False
        max_display_ms_ = current_option.obs_scene_max_display_ms

        elapsed_ms = (time.monotonic() - self._ctx.program_scene_since) * 1000.0
        if elapsed_ms < max_display_ms_:
            return False

        next_scene = self._pick_weighted_scene(cameras, current_scene)
        if not next_scene or next_scene == current_scene:
            return False

        try:
            await self._obs.set_program_scene(next_scene)
            self._ctx.program_scene_name = next_scene
            self._ctx.program_scene_since = time.monotonic()
            trace.switch_triggered = True
            trace.scene_max_display_triggered = True
            trace.rotated_scene = next_scene
            trace.winner = current_ctx.camera_id
            trace.winner_reason = f"SCENE_MAX_DISPLAY ({elapsed_ms:.0f}ms >= {max_display_ms_}ms)"

            self._ctx.record_switch(SwitchRecord(
                from_camera=current_ctx.camera_id,
                to_camera=current_ctx.camera_id,
                reason=trace.winner_reason,
                score=100.0,
                event_type=None,
            ))

            log.info(
                "decision_engine.scene_max_display_rotated",
                camera_id=current_ctx.camera_id,
                scene=next_scene,
                elapsed_ms=round(elapsed_ms, 0),
            )
            return True
        except Exception as e:
            log.error("decision_engine.scene_max_display_failed", error=str(e))
            return False

    async def _handle_obs_scene_camera_rotation(
        self,
        contexts: list[CameraContext],
        trace: DecisionTrace,
    ) -> bool:
        """Rotate OBS-scene cameras when the current camera hits its max display time."""
        if not self._ctx.program_camera_id:
            return False

        current_ctx = next(
            (ctx for ctx in contexts if ctx.camera_id == self._ctx.program_camera_id),
            None,
        )
        if not current_ctx or current_ctx.source_type != "obs_scene":
            return False

        max_display_ms = current_ctx.obs_scene_max_display_ms
        if max_display_ms <= 0:
            return False

        time_on_air_ms = self._ctx.time_on_current_camera_ms
        if time_on_air_ms < max_display_ms:
            return False

        candidates = [
            ctx for ctx in contexts
            if ctx.camera_id != current_ctx.camera_id
            and ctx.source_type == "obs_scene"
            and not ctx.is_in_cooldown
        ]
        winner = self._pick_weighted_camera(candidates)
        if winner is None:
            return False

        trace.winner = winner.camera_id
        trace.winner_score = winner.interest_score
        trace.winner_reason = (
            f"SCENE_MAX_DISPLAY ({time_on_air_ms:.0f}ms >= {max_display_ms}ms)"
        )
        trace.switch_triggered = True
        trace.scene_max_display_triggered = True
        trace.rotated_scene = winner.obs_scene_name

        await self._execute_switch(winner, trace)
        return True

    @staticmethod
    def _pick_weighted_camera(candidates: list[CameraContext]) -> Optional[CameraContext]:
        weighted = [c for c in candidates if c.obs_scene_weight > 0]
        if not weighted:
            return None
        total_weight = sum(c.obs_scene_weight for c in weighted)
        if total_weight <= 0:
            return None
        roll = random.uniform(0.0, total_weight)
        running = 0.0
        for candidate in weighted:
            running += candidate.obs_scene_weight
            if roll <= running:
                return candidate
        return weighted[-1]

    def _collect_scene_options(self, ctx: CameraContext) -> list[dict]:
        scene_map: Dict[str, dict] = {}
        for sub in ctx.subscriptions:
            if not sub.enabled:
                continue
            for option in sub.obs_scene_options:
                scene_name = option.scene_name.strip() if option.scene_name else ""
                if not scene_name or option.weight <= 0:
                    continue
                existing = scene_map.get(scene_name)
                if existing:
                    existing["weight"] += option.weight
                    existing["max_display_ms"] = max(existing["max_display_ms"], option.max_display_ms)
                else:
                    scene_map[scene_name] = {
                        "scene_name": scene_name,
                        "weight": option.weight,
                        "max_display_ms": option.max_display_ms,
                    }
        return list(scene_map.values())

    @staticmethod
    def _pick_weighted_scene(cameras: list[Camera], exclude_scene: Optional[str]) -> Optional[str]:
        candidates = [o for o in cameras if o.source_url != exclude_scene]
        if not candidates:
            return None
        total_weight = sum(o.obs_scene_weight for o in candidates)
        if total_weight <= 0:
            return None
        roll = random.uniform(0.0, total_weight)
        running = 0.0
        for option in candidates:
            running += option.obs_scene_weight
            if roll <= running:
                return option.source_url
        return candidates[-1].source_url

    def _pick_obs_scene(self, ctx: CameraContext) -> Optional[str]:
        event_type = ctx.pending_event_type or ctx.last_event_type
        if not event_type:
            return ctx.obs_scene_name.strip() if ctx.obs_scene_name else None
        sub = ctx.get_subscription(event_type)
        if not sub:
            return ctx.obs_scene_name.strip() if ctx.obs_scene_name else None
        options = [o for o in sub.obs_scene_options if o.scene_name and o.weight > 0]
        if not options:
            return ctx.obs_scene_name.strip() if ctx.obs_scene_name else None
        total_weight = sum(o.weight for o in options)
        roll = random.uniform(0.0, total_weight)
        running = 0.0
        for option in options:
            running += option.weight
            if roll <= running:
                return option.scene_name
        return options[-1].scene_name


# ── Singleton ─────────────────────────────────────────────────────────────────
decision_engine = RealizationDecisionEngine()
