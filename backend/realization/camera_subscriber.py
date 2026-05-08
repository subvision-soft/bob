"""
Camera Event Subscriber — Per-camera asyncio task.

Each camera gets its own subscriber that:
  1. Receives events from the global EventBus queue
  2. Filters by the camera's subscription config
  3. Updates the camera's CameraContext
  4. Computes new interest score
  5. Sets pending_transition state based on ReactionMode

This is the per-camera intelligence layer. All cameras run in parallel,
processing events independently — even cameras NOT currently on air.
"""

from __future__ import annotations

import asyncio
import time
from typing import Dict, Optional

import structlog

from backend.core.event_bus import event_bus
from backend.core.scoring import compute_score, ScoreBreakdown
from backend.events.models import CompetitionEvent
from backend.realization.camera_context import CameraContext, ReactionMode

log = structlog.get_logger(__name__)


class CameraEventSubscriber:
    """
    Subscribes to the global EventBus and processes events for one camera.
    Runs as a long-lived asyncio task.
    """

    def __init__(self, context: CameraContext) -> None:
        self._ctx = context
        self._queue: Optional[asyncio.Queue[CompetitionEvent]] = None
        self._running = False
        self._scores: Dict[str, ScoreBreakdown] = {}

    @property
    def camera_id(self) -> str:
        return self._ctx.camera_id

    @property
    def context(self) -> CameraContext:
        return self._ctx

    @property
    def last_score(self) -> Optional[ScoreBreakdown]:
        return self._scores.get("last")

    async def start(self) -> None:
        self._queue = await event_bus.subscribe(self.camera_id)
        self._running = True
        log.info("camera_subscriber.started", camera_id=self.camera_id)

    async def stop(self) -> None:
        self._running = False
        await event_bus.unsubscribe(self.camera_id)
        log.info("camera_subscriber.stopped", camera_id=self.camera_id)

    async def run(self) -> None:
        """Main event processing loop."""
        await self.start()
        try:
            while self._running:
                try:
                    event: CompetitionEvent = await asyncio.wait_for(
                        self._queue.get(), timeout=1.0
                    )
                except asyncio.TimeoutError:
                    # No event — decay interest score passively
                    self._apply_passive_decay()
                    continue

                await self._process_event(event)

        except asyncio.CancelledError:
            log.info("camera_subscriber.cancelled", camera_id=self.camera_id)
        finally:
            await self.stop()

    async def _process_event(self, event: CompetitionEvent) -> None:
        """
        Core event processing logic.
        - Check subscription
        - Update context
        - Compute score
        - Set pending state
        """
        target_camera_id = (
            event.raw_payload.get("target_camera_id")
            if isinstance(event.raw_payload, dict)
            else None
        )
        if target_camera_id and target_camera_id != self.camera_id:
            return

        sub = self._ctx.get_subscription(event.type)

        # Always push event to history (even if not subscribed, for global context)
        self._ctx.push_event(event)

        if sub is None:
            # Not subscribed → INFORM_ONLY effectively: update score passively
            log.debug(
                "camera_subscriber.event_ignored",
                camera_id=self.camera_id,
                event_type=event.type,
            )
            self._ctx.interest_score = max(
                0.0, self._ctx.interest_score * 0.9  # gradual decay
            )
            return

        log.info(
            "camera_subscriber.event_matched",
            camera_id=self.camera_id,
            event_type=event.type,
            mode=sub.mode,
            priority=sub.priority,
        )

        # ── Compute new score ──────────────────────────────────────────
        breakdown = compute_score(self._ctx, sub)
        self._ctx.interest_score = breakdown.total_score
        self._ctx.raw_score_components = breakdown.to_dict()
        self._scores["last"] = breakdown

        # ── Apply reaction mode ────────────────────────────────────────
        if sub.mode == ReactionMode.INFORM_ONLY:
            # Context updated, no transition signal
            pass

        elif sub.mode == ReactionMode.PREPARE:
            # Signal that this camera should be preloaded (preview / PTZ)
            self._ctx.pending_transition = True
            self._ctx.pending_mode = ReactionMode.PREPARE
            self._ctx.pending_since = time.monotonic()
            self._ctx.pending_event_type = event.type
            log.info("camera_subscriber.prepare_signal", camera_id=self.camera_id)

        elif sub.mode == ReactionMode.SWITCH_IF_HIGH_SCORE:
            # Let Decision Engine evaluate against threshold
            self._ctx.pending_transition = True
            self._ctx.pending_mode = ReactionMode.SWITCH_IF_HIGH_SCORE
            self._ctx.pending_since = time.monotonic()
            self._ctx.pending_event_type = event.type

        elif sub.mode == ReactionMode.FORCE_SWITCH:
            if not self._ctx.is_in_cooldown:
                self._ctx.pending_transition = True
                self._ctx.pending_mode = ReactionMode.FORCE_SWITCH
                self._ctx.pending_since = time.monotonic()
                self._ctx.pending_event_type = event.type
                log.info("camera_subscriber.force_switch_signal", camera_id=self.camera_id)
            else:
                log.info(
                    "camera_subscriber.force_switch_blocked_by_cooldown",
                    camera_id=self.camera_id,
                )

    def _apply_passive_decay(self) -> None:
        """Decay interest score when no event received (called on queue timeout)."""
        self._ctx.interest_score = max(0.0, self._ctx.interest_score * 0.95)


class CameraSubscriberRegistry:
    """
    Manages all CameraEventSubscriber instances.
    Creates/removes subscribers as cameras are added/removed from configuration.
    """

    def __init__(self) -> None:
        self._subscribers: Dict[str, CameraEventSubscriber] = {}
        self._tasks: Dict[str, asyncio.Task] = {}

    def get_subscriber(self, camera_id: str) -> Optional[CameraEventSubscriber]:
        return self._subscribers.get(camera_id)

    def get_all_contexts(self) -> list[CameraContext]:
        return [s.context for s in self._subscribers.values()]

    @property
    def subscriber_ids(self) -> list[str]:
        return list(self._subscribers.keys())

    async def register(self, context: CameraContext) -> CameraEventSubscriber:
        """Register a new camera subscriber and start its processing loop."""
        if context.camera_id in self._subscribers:
            return self._subscribers[context.camera_id]

        subscriber = CameraEventSubscriber(context)
        self._subscribers[context.camera_id] = subscriber

        task = asyncio.create_task(
            subscriber.run(),
            name=f"subscriber_{context.camera_id}",
        )
        self._tasks[context.camera_id] = task

        log.info("subscriber_registry.registered", camera_id=context.camera_id)
        return subscriber

    async def unregister(self, camera_id: str) -> None:
        task = self._tasks.pop(camera_id, None)
        if task:
            task.cancel()
            try:
                await task
            except (asyncio.CancelledError, Exception):
                pass
        self._subscribers.pop(camera_id, None)
        log.info("subscriber_registry.unregistered", camera_id=camera_id)

    async def stop_all(self) -> None:
        for camera_id in list(self._tasks.keys()):
            await self.unregister(camera_id)


# ── Singleton ─────────────────────────────────────────────────────────────────
subscriber_registry = CameraSubscriberRegistry()
