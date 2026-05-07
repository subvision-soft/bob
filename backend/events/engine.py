"""
Event Engine — Polls the external Competition API and publishes events to the bus.

Key responsibilities:
  - Periodic polling at configurable interval (default 100ms)
  - Deduplication via (external_id, type) hash set with TTL expiry
  - Frame-timestamp association: each event gets the monotonic timestamp
    of the most recently ingested video frame (supplied by VideoIngestWorker)
  - Circuit breaker: backs off on repeated API failures
  - Structured logging of every received/dropped event
"""

from __future__ import annotations

import asyncio
import hashlib
import time
from collections import deque
from typing import Any, Deque, Dict, List, Optional, Set, Tuple

import httpx
import structlog

from backend.core.event_bus import event_bus
from backend.core.settings import get_settings
from backend.events.models import CompetitionEvent, EventType

log = structlog.get_logger(__name__)
settings = get_settings()

# ── Deduplication window ──────────────────────────────────────────────────────
DEDUP_WINDOW_SECONDS = 5.0
DEDUP_MAX_SIZE = 1000


class DeduplicationCache:
    """
    Rolling time-window deduplication cache.
    Stores (hash, timestamp) tuples; expires entries older than DEDUP_WINDOW_SECONDS.
    """

    def __init__(self, window_s: float = DEDUP_WINDOW_SECONDS) -> None:
        self._window = window_s
        self._cache: Deque[Tuple[str, float]] = deque(maxlen=DEDUP_MAX_SIZE)
        self._hashes: Set[str] = set()

    def is_duplicate(self, event: CompetitionEvent) -> bool:
        self._evict_expired()
        key = self._make_key(event)
        return key in self._hashes

    def add(self, event: CompetitionEvent) -> None:
        key = self._make_key(event)
        self._cache.append((key, time.monotonic()))
        self._hashes.add(key)

    def _evict_expired(self) -> None:
        now = time.monotonic()
        while self._cache and (now - self._cache[0][1]) > self._window:
            expired_key, _ = self._cache.popleft()
            self._hashes.discard(expired_key)

    @staticmethod
    def _make_key(event: CompetitionEvent) -> str:
        # Use external_id if present, otherwise hash type+payload
        if event.external_id:
            return f"{event.type}:{event.external_id}"
        payload_str = str(sorted(event.raw_payload.items()))
        return hashlib.md5(f"{event.type}:{payload_str}".encode()).hexdigest()


class CircuitBreaker:
    """Simple circuit breaker for the external API client."""

    def __init__(self, failure_threshold: int = 5, recovery_timeout_s: float = 30.0) -> None:
        self._failure_threshold = failure_threshold
        self._recovery_timeout = recovery_timeout_s
        self._failures = 0
        self._opened_at: Optional[float] = None

    @property
    def is_open(self) -> bool:
        if self._opened_at is None:
            return False
        if time.monotonic() - self._opened_at > self._recovery_timeout:
            self._reset()
            return False
        return True

    def record_success(self) -> None:
        self._failures = 0
        self._opened_at = None

    def record_failure(self) -> None:
        self._failures += 1
        if self._failures >= self._failure_threshold:
            self._opened_at = time.monotonic()
            log.warning("circuit_breaker.opened", failures=self._failures)

    def _reset(self) -> None:
        self._failures = 0
        self._opened_at = None
        log.info("circuit_breaker.closed")


class EventEngine:
    """
    Polls the external Competition API and publishes normalized events
    to the global EventBus.
    """

    def __init__(self) -> None:
        self._dedup = DeduplicationCache()
        self._breaker = CircuitBreaker()
        self._last_frame_ts: float = time.monotonic()
        self._last_frame_id: int = 0
        self._poll_interval = settings.external_api_poll_interval_ms / 1000.0
        self._client: Optional[httpx.AsyncClient] = None
        self._stats = {
            "polled": 0,
            "received": 0,
            "published": 0,
            "duplicates": 0,
            "errors": 0,
        }

    def update_frame_cursor(self, frame_id: int, timestamp: float) -> None:
        """Called by VideoIngestWorker to keep the frame cursor up to date."""
        self._last_frame_id = frame_id
        self._last_frame_ts = timestamp

    async def start(self) -> None:
        self._client = httpx.AsyncClient(
            base_url=settings.external_api_url,
            timeout=settings.external_api_timeout_s,
            headers={"X-Api-Key": settings.external_api_key} if settings.external_api_key else {},
        )

    async def stop(self) -> None:
        if self._client:
            await self._client.aclose()

    async def poll_once(self) -> List[CompetitionEvent]:
        """Fetch new events from the external API. Returns normalized events."""
        if self._breaker.is_open:
            log.debug("event_engine.circuit_open_skip")
            return []

        self._stats["polled"] += 1
        try:
            response = await self._client.get("/events/pending")
            response.raise_for_status()
            self._breaker.record_success()

            raw_events: List[Dict[str, Any]] = response.json()
            events: List[CompetitionEvent] = []

            for raw in raw_events:
                self._stats["received"] += 1
                event = CompetitionEvent.from_external(raw)

                if self._dedup.is_duplicate(event):
                    self._stats["duplicates"] += 1
                    continue

                # Attach frame correlation
                event.frame_id = self._last_frame_id
                event.frame_timestamp = self._last_frame_ts

                self._dedup.add(event)
                events.append(event)

            return events

        except httpx.HTTPStatusError as e:
            self._stats["errors"] += 1
            self._breaker.record_failure()
            log.warning("event_engine.http_error", status=e.response.status_code)
            return []
        except httpx.RequestError as e:
            self._stats["errors"] += 1
            self._breaker.record_failure()
            log.warning("event_engine.request_error", error=str(e))
            return []

    async def run(self) -> None:
        """Main polling loop."""
        await self.start()
        log.info("event_engine.started", poll_interval_ms=settings.external_api_poll_interval_ms)

        try:
            while True:
                loop_start = time.monotonic()

                events = await self.poll_once()
                for event in events:
                    delivered = await event_bus.publish(event)
                    self._stats["published"] += 1
                    log.info(
                        "event_engine.published",
                        event_type=event.type,
                        event_id=event.id,
                        delivered_to=delivered,
                    )

                # Adaptive sleep: subtract time already spent in this iteration
                elapsed = time.monotonic() - loop_start
                sleep_time = max(0.0, self._poll_interval - elapsed)
                await asyncio.sleep(sleep_time)

        except asyncio.CancelledError:
            log.info("event_engine.cancelled")
        finally:
            await self.stop()

    @property
    def stats(self) -> Dict[str, int]:
        return dict(self._stats)


# ── Singleton ─────────────────────────────────────────────────────────────────
event_engine = EventEngine()
