"""
Global Event Bus — Gabin-inspired fan-out pub/sub for Subvision Studio.

Architecture:
  - One producer: EventPollerWorker publishes CompetitionEvent objects.
  - N consumers: CameraEventSubscriber tasks (one per camera).
  - Each subscriber gets its own asyncio.Queue for decoupled processing.
  - Backpressure: if a subscriber queue is full, the event is dropped for that
    subscriber and a warning is logged (non-blocking broadcast).

Design inspired by Gabin's EventEmitter pattern (Node.js EventEmitter adapted
to Python asyncio). Key difference: Python asyncio requires explicit queue-per-
subscriber instead of in-process event listeners.
"""

from __future__ import annotations

import asyncio
from collections import defaultdict
from typing import Dict, List, Optional

import structlog

from backend.events.models import CompetitionEvent

log = structlog.get_logger(__name__)

QUEUE_MAX_SIZE = 256  # max backlog per subscriber


class EventBus:
    """
    Asyncio-based publish/subscribe event bus.

    Usage:
        bus = EventBus()
        queue = bus.subscribe("camera_1")
        await bus.publish(event)
        event = await queue.get()
    """

    def __init__(self) -> None:
        self._subscribers: Dict[str, asyncio.Queue[CompetitionEvent]] = {}
        self._lock = asyncio.Lock()
        self._stats: Dict[str, int] = defaultdict(int)

    async def subscribe(self, subscriber_id: str) -> asyncio.Queue[CompetitionEvent]:
        """Register a subscriber and return its dedicated queue."""
        async with self._lock:
            if subscriber_id in self._subscribers:
                log.warning("event_bus.already_subscribed", subscriber_id=subscriber_id)
                return self._subscribers[subscriber_id]
            queue: asyncio.Queue[CompetitionEvent] = asyncio.Queue(maxsize=QUEUE_MAX_SIZE)
            self._subscribers[subscriber_id] = queue
            log.info("event_bus.subscribed", subscriber_id=subscriber_id)
            return queue

    async def unsubscribe(self, subscriber_id: str) -> None:
        async with self._lock:
            self._subscribers.pop(subscriber_id, None)
            log.info("event_bus.unsubscribed", subscriber_id=subscriber_id)

    async def publish(self, event: CompetitionEvent) -> int:
        """
        Fan-out: publish event to ALL subscriber queues.
        Returns number of subscribers that received the event.
        Non-blocking: drops to full queues with a warning.
        """
        delivered = 0
        dropped = 0

        async with self._lock:
            subscribers = dict(self._subscribers)

        for sid, queue in subscribers.items():
            try:
                queue.put_nowait(event)
                self._stats[sid] += 1
                delivered += 1
            except asyncio.QueueFull:
                dropped += 1
                log.warning(
                    "event_bus.queue_full_drop",
                    subscriber_id=sid,
                    event_type=event.type,
                )

        log.debug(
            "event_bus.published",
            event_type=event.type,
            event_id=event.id,
            delivered=delivered,
            dropped=dropped,
        )
        return delivered

    @property
    def subscriber_ids(self) -> List[str]:
        return list(self._subscribers.keys())

    def stats(self) -> Dict[str, int]:
        return dict(self._stats)

    def queue_sizes(self) -> Dict[str, int]:
        return {sid: q.qsize() for sid, q in self._subscribers.items()}


# ── Singleton instance shared across the application ──────────────────────────
event_bus = EventBus()
