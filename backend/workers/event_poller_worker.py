"""
Event Poller Worker — Asyncio task that drives the Event Engine polling loop.
Loads cameras from DB on startup to initialize subscriber registry.
"""

from __future__ import annotations

import asyncio

import structlog
from sqlalchemy import select

from backend.database import AsyncSessionLocal
from backend.events.engine import event_engine
from backend.models import Camera
from backend.api.cameras import _register_camera_subscriber

log = structlog.get_logger(__name__)


class EventPollerWorker:
    async def run(self) -> None:
        # Load all cameras from DB and register subscribers
        async with AsyncSessionLocal() as db:
            result = await db.execute(select(Camera).where(Camera.enabled == True))
            cameras = result.scalars().all()
            log.info("event_poller_worker.loading_cameras", count=len(cameras))
            for camera in cameras:
                await _register_camera_subscriber(camera)

        # Start the polling engine
        await event_engine.run()
