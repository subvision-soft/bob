"""
Video Ingest Worker — Multi-stream OpenCV/FFmpeg capture manager.

Responsibilities:
  - Open RTSP/webcam streams for all configured cameras
  - Extract frames and update EventEngine frame cursor
  - Expose latest JPEG snapshots for browser preview
  - Monitor stream health (FPS, drop rate, latency)
  - Broadcast stream health via WebSocket
"""

from __future__ import annotations

import asyncio
import time
from collections import defaultdict
from typing import Dict, Optional

import structlog

from backend.core.settings import get_settings

log = structlog.get_logger(__name__)
settings = get_settings()


class StreamStats:
    def __init__(self) -> None:
        self.fps: float = 0.0
        self.frames_received: int = 0
        self.frames_dropped: int = 0
        self.last_frame_at: float = 0.0
        self.latency_ms: float = 0.0
        self.status: str = "IDLE"  # IDLE | CONNECTING | OK | ERROR


# Global snapshot store: camera_id → latest JPEG bytes
_snapshots: Dict[str, bytes] = {}
_stream_stats: Dict[str, StreamStats] = defaultdict(StreamStats)
_frame_counter: int = 0


def get_snapshot(camera_id: str) -> Optional[bytes]:
    return _snapshots.get(camera_id)


def get_all_stats() -> dict:
    return {
        cid: {
            "fps": round(s.fps, 1),
            "frames_received": s.frames_received,
            "frames_dropped": s.frames_dropped,
            "latency_ms": round(s.latency_ms, 1),
            "status": s.status,
        }
        for cid, s in _stream_stats.items()
    }


class CameraStream:
    """
    Single camera RTSP/webcam stream managed via OpenCV in a thread executor.
    Keeps the event loop non-blocking by running cv2.VideoCapture in threads.
    """

    def __init__(self, camera_id: str, source_url: str) -> None:
        self.camera_id = camera_id
        self.source_url = source_url
        self._running = False
        self._cap = None

    async def open(self) -> bool:
        try:
            import cv2  # type: ignore

            def _open():
                cap = cv2.VideoCapture(self.source_url)
                return cap if cap.isOpened() else None

            self._cap = await asyncio.to_thread(_open)
            if self._cap:
                _stream_stats[self.camera_id].status = "OK"
                log.info("video_ingest.stream_opened", camera_id=self.camera_id)
                return True
        except Exception as e:
            log.error("video_ingest.open_failed", camera_id=self.camera_id, error=str(e))
        _stream_stats[self.camera_id].status = "ERROR"
        return False

    async def read_frame(self) -> Optional[bytes]:
        """Read one frame and encode to JPEG. Returns None on failure."""
        if not self._cap:
            return None
        try:
            import cv2
            import numpy as np  # noqa

            def _read():
                ret, frame = self._cap.read()
                if not ret:
                    return None
                _, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 75])
                return buf.tobytes()

            return await asyncio.to_thread(_read)
        except Exception as e:
            log.warning("video_ingest.read_frame_failed", camera_id=self.camera_id, error=str(e))
            return None

    async def close(self) -> None:
        if self._cap:
            await asyncio.to_thread(self._cap.release)
            self._cap = None


    def __init__(self) -> None:
        self._streams: Dict[str, CameraStream] = {}

    async def _sync_streams(self) -> None:
        from sqlalchemy import select
        from backend.database import AsyncSessionLocal
        from backend.models import Camera

        async with AsyncSessionLocal() as session:
            result = await session.execute(
                select(Camera).where(Camera.enabled == True, Camera.source_url.is_not(None))
            )
            cameras = result.scalars().all()

        active_ids = {c.id for c in cameras}

        # Start new streams
        for cam in cameras:
            if cam.id not in self._streams and cam.source_url:
                stream = CameraStream(cam.id, cam.source_url)
                self._streams[cam.id] = stream
                await stream.open()

        # Stop removed streams
        for cam_id in list(self._streams.keys()):
            if cam_id not in active_ids:
                stream = self._streams.pop(cam_id)
                await stream.close()
                _stream_stats.pop(cam_id, None)

    async def _capture_loop(self) -> None:
        # Loop over all active streams and capture one frame
        for cam_id, stream in list(self._streams.items()):
            start_time = time.monotonic()
            frame_bytes = await stream.read_frame()
            elapsed_ms = (time.monotonic() - start_time) * 1000

            stats = _stream_stats[cam_id]
            if frame_bytes:
                _snapshots[cam_id] = frame_bytes
                stats.frames_received += 1
                stats.last_frame_at = time.time()
                stats.latency_ms = elapsed_ms
                
                # Simple FPS calculation over time
                if stats.frames_received % 10 == 0:
                    stats.fps = 10.0 / max(0.001, (time.time() - stats.last_frame_at + 10 * elapsed_ms / 1000.0))
            else:
                stats.frames_dropped += 1

    async def run(self) -> None:
        log.info("video_ingest_worker.started")
        try:
            while True:
                await self._sync_streams()
                await self._capture_loop()
                await asyncio.sleep(settings.video_snapshot_interval_ms / 1000.0)
        except asyncio.CancelledError:
            log.info("video_ingest_worker.cancelled")
            for stream in self._streams.values():
                await stream.close()
