"""
Event Poller Worker — Asyncio task that drives the Event Engine polling loop.
Loads cameras from DB on startup to initialize subscriber registry.
"""

from __future__ import annotations

import asyncio

import structlog
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from backend.database import AsyncSessionLocal
from backend.events.engine import event_engine
from backend.models import Camera, CameraSubscriptionModel
from backend.api.cameras import _register_camera_subscriber
from backend.core.camera_registry import camera_registry

log = structlog.get_logger(__name__)


class EventPollerWorker:
    async def run(self) -> None:
        try:
            # Load all cameras from DB and register subscribers
            async with AsyncSessionLocal() as db:
                result = await db.execute(
                    select(Camera)
                    .where(Camera.enabled == True)
                    .options(
                        selectinload(Camera.subscriptions).selectinload(CameraSubscriptionModel.obs_scene_options),
                    )
                )
                cameras = result.scalars().all()
                log.info("event_poller_worker.loading_cameras", count=len(cameras))
                await camera_registry.set_all(cameras)
                for camera in cameras:
                    await _register_camera_subscriber(camera)

            log.info("event_poller_worker.starting_engine")
            # Start the polling engine
            await event_engine.run()
        except asyncio.CancelledError:
            log.info("event_poller_worker.cancelled")
            raise
        except Exception as e:
            log.exception("event_poller_worker.failed", error=str(e))
            raise
