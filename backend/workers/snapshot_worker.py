"""
Snapshot Worker — Periodically broadcasts camera snapshots and stream health
to all WebSocket clients so the Angular UI can display live previews.
"""

from __future__ import annotations

import asyncio
import base64
import time

import structlog

from backend.core.settings import get_settings
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
                for ctx in subscriber_registry.get_all_contexts():
                    jpeg = get_snapshot(ctx.camera_id)
                    if jpeg:
                        await ws_manager.broadcast({
                            "type": "snapshot",
                            "camera_id": ctx.camera_id,
                            "data": base64.b64encode(jpeg).decode(),
                            "ts": time.time(),
                        })

        except asyncio.CancelledError:
            log.info("snapshot_worker.cancelled")
