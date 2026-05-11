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
import base64
import time
from collections import defaultdict
from typing import Dict, Optional

import structlog

from backend.events.engine import event_engine
from backend.core.settings import get_settings
from backend.obs.client import get_obs_client

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

class VideoIngestWorker:
    """
    Manages all camera streams. Publishes JPEG snapshots and
    updates the EventEngine frame cursor for event correlation.
    """
    def __init__(self) -> None:
        self._streams: Dict[str, CameraStream] = {}
        self._obs_scene_sources: Dict[str, str] = {}

    async def _sync_streams(self) -> None:
        from sqlalchemy import select
        from backend.database import AsyncSessionLocal
        from backend.models import Camera

        async with AsyncSessionLocal() as session:
            result = await session.execute(
                select(Camera).where(Camera.enabled == True)
            )
            cameras = result.scalars().all()

        active_stream_ids = set()
        obs_scene_sources: Dict[str, str] = {}

        # Start / keep RTSP or file streams
        for cam in cameras:
            if cam.source_type == "obs_scene":
                scene_name = cam.obs_scene_name or cam.source_url or cam.name
                if scene_name:
                    obs_scene_sources[cam.id] = scene_name
                    _stream_stats[cam.id].status = "OK"
                continue

            if not cam.source_url:
                continue

            active_stream_ids.add(cam.id)
            if cam.id not in self._streams:
                stream = CameraStream(cam.id, cam.source_url)
                self._streams[cam.id] = stream
                await stream.open()

        # Stop removed streams
        for cam_id in list(self._streams.keys()):
            if cam_id not in active_stream_ids:
                stream = self._streams.pop(cam_id)
                await stream.close()
                _stream_stats.pop(cam_id, None)

        self._obs_scene_sources = obs_scene_sources

    async def _capture_loop(self) -> None:
        global _frame_counter

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
                _frame_counter += 1
                event_engine.update_frame_cursor(cam_id, _frame_counter, time.monotonic(), frame_bytes)
                
                # Simple FPS calculation over time
                if stats.frames_received % 10 == 0:
                    stats.fps = 10.0 / max(0.001, (time.time() - stats.last_frame_at + 10 * elapsed_ms / 1000.0))
            else:
                stats.frames_dropped += 1

        # Ingest OBS scene snapshots as frames for obs_scene cameras
        if self._obs_scene_sources:
            obs_client = get_obs_client()
            if not obs_client.is_connected:
                for cam_id in self._obs_scene_sources:
                    _stream_stats[cam_id].status = "ERROR"
                return

            for cam_id, scene_name in self._obs_scene_sources.items():
                stats = _stream_stats[cam_id]
                start_time = time.monotonic()
                try:
                    image_data = await obs_client.get_scene_snapshot(scene_name)
                except Exception as e:
                    stats.frames_dropped += 1
                    stats.status = "ERROR"
                    log.warning("video_ingest.obs_snapshot_failed", camera_id=cam_id, scene_name=scene_name, error=str(e))
                    continue

                if not image_data:
                    stats.frames_dropped += 1
                    continue

                try:
                    frame_bytes = base64.b64decode(image_data)
                except Exception:
                    stats.frames_dropped += 1
                    log.warning("video_ingest.obs_snapshot_decode_failed", camera_id=cam_id, scene_name=scene_name)
                    continue

                elapsed_ms = (time.monotonic() - start_time) * 1000
                _snapshots[cam_id] = frame_bytes
                stats.frames_received += 1
                stats.last_frame_at = time.time()
                stats.latency_ms = elapsed_ms
                stats.status = "OK"

                _frame_counter += 1
                event_engine.update_frame_cursor(cam_id, _frame_counter, time.monotonic(), frame_bytes)

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
