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
import base64
import hashlib
from dataclasses import dataclass
from datetime import datetime, timezone
import time
from collections import deque
from typing import Any, Deque, Dict, List, Optional, Set, Tuple

import httpx
import structlog

from backend.core.event_bus import event_bus
from backend.realization.camera_subscriber import subscriber_registry
from backend.core.settings import get_settings
from backend.events.models import CompetitionEvent, EventType

log = structlog.get_logger(__name__)
settings = get_settings()

# ── Deduplication window ──────────────────────────────────────────────────────
DEDUP_WINDOW_SECONDS = 5.0
DEDUP_MAX_SIZE = 1000


@dataclass
class FrameSample:
    frame_id: int
    timestamp: float
    image_data: str


@dataclass
class FrameWindow:
    samples: Deque[FrameSample]
    updated_at: float = 0.0

    def __init__(self) -> None:
        # Keep history by time (pruned in update_frame_cursor), not by fixed count.
        self.samples = deque()
        self.updated_at = 0.0


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
        self._frame_windows: Dict[str, FrameWindow] = {}
        self._poll_interval = settings.external_api_poll_interval_ms / 1000.0
        self._client: Optional[httpx.AsyncClient] = None
        self._auth_token: Optional[str] = None
        self._auth_token_expires_at: Optional[float] = None
        self._last_api_call_time: Dict[str, float] = {}  # camera_id -> last API call timestamp
        self._api_call_throttle_s = 1.0  # Call API once per second per camera
        self._frame_compare_delta_s = 1.0  # Compare current frame with frame from ~1s earlier
        self._frame_history_keep_s = 3.0
        self._last_skip_reason: Dict[str, str] = {}
        self._stats = {
            "polled": 0,
            "received": 0,
            "published": 0,
            "duplicates": 0,
            "errors": 0,
        }

    def update_frame_cursor(self, camera_id: str, frame_id: int, timestamp: float, image_data: bytes) -> None:
        """Called by VideoIngestWorker to keep the per-camera two-frame window up to date."""
        window = self._frame_windows.setdefault(camera_id, FrameWindow())
        sample = FrameSample(
            frame_id=frame_id,
            timestamp=timestamp,
            image_data=base64.b64encode(image_data).decode(),
        )
        window.samples.append(sample)

        # Keep only a short rolling history used for 1-second comparisons.
        min_timestamp = timestamp - self._frame_history_keep_s
        while window.samples and window.samples[0].timestamp < min_timestamp:
            window.samples.popleft()

        window.updated_at = time.monotonic()

    def _candidate_camera_ids(self) -> List[str]:
        # Primary source: all registered subscribers (configured cameras).
        subscriber_ids = list(subscriber_registry.subscriber_ids)
        if subscriber_ids:
            # Keep deterministic order: newest frame windows first when available.
            return sorted(
                subscriber_ids,
                key=lambda cid: self._frame_windows.get(cid).updated_at if cid in self._frame_windows else 0.0,
                reverse=True,
            )

        # Fallback: if no subscribers are registered yet, use frame windows.
        if not self._frame_windows:
            return []
        items = sorted(self._frame_windows.items(), key=lambda item: item[1].updated_at, reverse=True)
        return [camera_id for camera_id, _ in items]

    def _should_call_api(self, camera_id: str) -> bool:
        """Check if we should call the API for this camera (throttle to ~1s)."""
        now = time.monotonic()
        last_call = self._last_api_call_time.get(camera_id, 0)
        return (now - last_call) >= self._api_call_throttle_s

    def _record_api_call(self, camera_id: str) -> None:
        """Record that we made an API call for this camera."""
        self._last_api_call_time[camera_id] = time.monotonic()

    def _frame_window_payload(self, camera_id: str) -> Optional[Dict[str, Any]]:
        if camera_id not in self._frame_windows:
            self._last_skip_reason[camera_id] = "no_frame_window"
            return None

        # Throttle API calls to once per second per camera
        if not self._should_call_api(camera_id):
            self._last_skip_reason[camera_id] = "throttled"
            return None

        window = self._frame_windows.get(camera_id)
        if not window or len(window.samples) < 2:
            self._last_skip_reason[camera_id] = "insufficient_samples"
            return None

        current = window.samples[-1]
        target_timestamp = current.timestamp - self._frame_compare_delta_s
        previous: Optional[FrameSample] = None
        for sample in reversed(list(window.samples)[:-1]):
            if sample.timestamp <= target_timestamp:
                previous = sample
                break

        # Not enough history yet to build a ~1-second frame pair.
        if previous is None:
            self._last_skip_reason[camera_id] = "no_1s_previous_frame"
            return None

        # If there is no active subscriber or no enabled subscriptions for this camera,
        # skip calling the external detection API to avoid unnecessary work.
        subscriber = subscriber_registry.get_subscriber(camera_id)
        subscriptions: Optional[List[str]] = None
        if subscriber is None:
            self._last_skip_reason[camera_id] = "no_subscriber"
            return None
        # Extract enabled subscription event types
        ctx = subscriber.context
        subscriptions = [s.event_type for s in ctx.subscriptions if s.enabled]
        if not subscriptions:
            self._last_skip_reason[camera_id] = "no_enabled_subscriptions"
            return None

        # Record the API call time for throttling
        self._record_api_call(camera_id)
        self._last_skip_reason[camera_id] = "ready"

        return {
            "camera_id": camera_id,
            "subscriptions": subscriptions,
            "previous_frame": {
                "frame_id": previous.frame_id,
                "timestamp": previous.timestamp,
                "image_data": previous.image_data,
            },
            "current_frame": {
                "frame_id": current.frame_id,
                "timestamp": current.timestamp,
                "image_data": current.image_data,
            },
        }

    async def _fetch_token(self) -> None:
        async with httpx.AsyncClient(
            timeout=settings.external_api_timeout_s,
            follow_redirects=True,
        ) as client:
            response = await client.get(settings.external_api_token_url)
            response.raise_for_status()
            data = response.json()

        self._auth_token = data.get("token")
        expires_at = data.get("expiration")
        self._auth_token_expires_at = None
        if isinstance(expires_at, str):
            try:
                parsed = datetime.fromisoformat(expires_at)
                if parsed.tzinfo is None:
                    parsed = parsed.replace(tzinfo=timezone.utc)
                self._auth_token_expires_at = parsed.timestamp()
            except ValueError:
                self._auth_token_expires_at = None

    async def _ensure_token(self) -> None:
        if not self._auth_token:
            await self._fetch_token()
            return
        if self._auth_token_expires_at and (time.time() >= self._auth_token_expires_at - 30):
            await self._fetch_token()

    def _auth_headers(self) -> Dict[str, str]:
        if not self._auth_token:
            return {}
        return {"Authorization": f"Bearer {self._auth_token}"}

    async def start(self) -> None:
        await self._ensure_token()
        self._client = httpx.AsyncClient(
            base_url=settings.external_api_url,
            timeout=settings.external_api_timeout_s,
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
        events: List[CompetitionEvent] = []
        try:
            camera_ids = self._candidate_camera_ids()
            if not camera_ids:
                log.debug("event_engine.poll_skip", reason="no_subscribers_or_camera_windows")
                return []

            for camera_id in camera_ids:
                payload = self._frame_window_payload(camera_id)
                if payload is None:
                    log.debug("event_engine.poll_skip", camera_id=camera_id, reason=self._last_skip_reason.get(camera_id, "unknown"))
                    continue

                log.debug("event_engine.polling")
                response = await self._client.post(
                    "/events/pending",
                    json=payload,
                    headers=self._auth_headers(),
                )
                if response.status_code == 401:
                    await self._fetch_token()
                    response = await self._client.post(
                        "/events/pending",
                        json=payload,
                        headers=self._auth_headers(),
                    )
                response.raise_for_status()
                self._breaker.record_success()

                raw_events: List[Dict[str, Any]] = response.json()
                for raw in raw_events:
                    self._stats["received"] += 1
                    event = CompetitionEvent.from_external(raw)


                    if self._dedup.is_duplicate(event):
                        self._stats["duplicates"] += 1
                        continue

                    # Attach frame correlation
                    if event.frame_id is None:
                        event.frame_id = payload["current_frame"]["frame_id"]
                    if event.frame_timestamp is None:
                        event.frame_timestamp = payload["current_frame"]["timestamp"]

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
