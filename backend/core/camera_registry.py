"""
Camera Registry — In-memory snapshot of all cameras.

Keeps a cached list of cameras updated from DB and API mutations.
"""

from __future__ import annotations

import asyncio
from typing import Dict, List, Optional

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from backend.database import AsyncSessionLocal
from backend.models import Camera, CameraSubscriptionModel


class CameraRegistry:
    def __init__(self) -> None:
        self._lock = asyncio.Lock()
        self._cameras: List[Camera] = []
        self._by_id: Dict[str, Camera] = {}

    async def refresh(self) -> None:
        async with AsyncSessionLocal() as session:
            result = await session.execute(
                select(Camera).options(
                    selectinload(Camera.subscriptions).selectinload(
                        CameraSubscriptionModel.obs_scene_options
                    ),
                )
            )
            cameras = result.scalars().all()
        await self.set_all(cameras)

    async def set_all(self, cameras: List[Camera]) -> None:
        async with self._lock:
            self._cameras = list(cameras)
            self._by_id = {c.id: c for c in cameras}

    async def upsert(self, camera: Camera) -> None:
        async with self._lock:
            existing = self._by_id.get(camera.id)
            if existing:
                self._cameras = [c for c in self._cameras if c.id != camera.id]
            self._cameras.append(camera)
            self._by_id[camera.id] = camera

    async def remove(self, camera_id: str) -> None:
        async with self._lock:
            self._by_id.pop(camera_id, None)
            self._cameras = [c for c in self._cameras if c.id != camera_id]

    def get_all(self) -> List[Camera]:
        return list(self._cameras)

    def get_by_id(self, camera_id: str) -> Optional[Camera]:
        return self._by_id.get(camera_id)


camera_registry = CameraRegistry()
