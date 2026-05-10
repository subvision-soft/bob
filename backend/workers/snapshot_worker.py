"""
Snapshot Worker — Periodically broadcasts camera snapshots and stream health
to all WebSocket clients so the Angular UI can display live previews.
"""

from __future__ import annotations

import asyncio
import base64
import time
from typing import Dict, Optional

import structlog

from backend.core.settings import get_settings
from sqlalchemy import select

from backend.database import AsyncSessionLocal
from backend.models import Camera
from backend.obs.client import get_obs_client
from backend.websocket.manager import ws_manager
from backend.workers.video_ingest_worker import get_all_stats, get_snapshot, _stream_stats
from backend.realization.camera_subscriber import subscriber_registry
from backend.core.context_manager import global_context

log = structlog.get_logger(__name__)
settings = get_settings()


class SnapshotWorker:
    """
    Periodic broadcast loop:
    - Every snapshot_interval_ms: sends camera JPEG previews (base64) + stream health
    - Every 1s: sends camera_scores update to all clients
    """

    async def run(self) -> None:
        log.info("snapshot_worker.started")
        tick = 0
        camera_info: Dict[str, Dict[str, Optional[str]]] = {}
        last_camera_refresh = 0.0
        camera_refresh_interval_s = 5.0

        async def _refresh_cameras() -> None:
            nonlocal camera_info, last_camera_refresh
            now = time.monotonic()
            if now - last_camera_refresh < camera_refresh_interval_s:
                return
            async with AsyncSessionLocal() as db:
                result = await db.execute(
                    select(
                        Camera.id,
                        Camera.source_type,
                        Camera.source_url,
                        Camera.obs_scene_name,
                    ).where(Camera.enabled == True)
                )
                rows = result.all()
            camera_info = {
                cam_id: {
                    "source_type": source_type,
                    "source_url": source_url,
                    "obs_scene_name": obs_scene_name,
                }
                for cam_id, source_type, source_url, obs_scene_name in rows
            }
            last_camera_refresh = now

        try:
            while True:
                await asyncio.sleep(settings.video_snapshot_interval_ms / 1000.0)
                tick += 1

                # ── Stream health broadcast ────────────────────────────
                stream_stats = get_all_stats()
                if stream_stats:
                    await ws_manager.broadcast({
                        "type": "stream_health",
                        "data": stream_stats,
                        "ts": time.time(),
                    })

                # ── Camera scores broadcast (every other tick ~1s) ─────
                if tick % 2 == 0:
                    scores = [ctx.to_dict() for ctx in subscriber_registry.get_all_contexts()]
                    await ws_manager.broadcast({
                        "type": "camera_scores",
                        "data": scores,
                        "ts": time.time(),
                    })

                # ── Global context broadcast (every 2s) ───────────────
                if tick % 4 == 0:
                    await ws_manager.broadcast({
                        "type": "global_context",
                        "data": global_context.to_dict(),
                        "ts": time.time(),
                    })

                # ── JPEG snapshot broadcast ───────────────────────────
                await _refresh_cameras()
                obs_client = get_obs_client()
                for camera_id, info in camera_info.items():
                    jpeg = get_snapshot(camera_id)
                    if jpeg:
                        await ws_manager.broadcast({
                            "type": "snapshot",
                            "camera_id": camera_id,
                            "data": base64.b64encode(jpeg).decode(),
                            "ts": time.time(),
                        })
                        continue

                    if info.get("source_type") != "obs_scene":
                        continue

                    scene_name = info.get("obs_scene_name") or info.get("source_url")
                    if not scene_name or not obs_client.is_connected:
                        continue
                    try:
                        image_data = await obs_client.get_scene_snapshot(scene_name)
                    except Exception as e:
                        log.warning(
                            "snapshot_worker.obs_snapshot_failed",
                            camera_id=camera_id,
                            scene_name=scene_name,
                            error=str(e),
                        )
                        continue
                    if image_data:
                        await ws_manager.broadcast({
                            "type": "snapshot",
                            "camera_id": camera_id,
                            "data": image_data,
                            "ts": time.time(),
                        })

        except asyncio.CancelledError:
            log.info("snapshot_worker.cancelled")
