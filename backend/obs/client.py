"""
OBS WebSocket Client — Async wrapper for obs-websocket protocol v5.

Handles:
  - Connection + reconnection
  - Scene switching (program + preview)
  - Transition management
  - Scene/source listing
  - Overlay control
  - Connection state broadcasting
"""

from __future__ import annotations

import asyncio
import time
from typing import Any, Callable, Coroutine, Dict, List, Optional, TYPE_CHECKING

import structlog
from obswebsocket import obsws, requests as obs_requests, events as obs_events  # type: ignore

from backend.core.camera_registry import camera_registry
from backend.core.context_manager import SwitchRecord, global_context
from backend.database import AsyncSessionLocal
from backend.models import Camera
from backend.realization.camera_subscriber import subscriber_registry
from backend.websocket.manager import ws_manager
from sqlalchemy import select

log = structlog.get_logger(__name__)

if TYPE_CHECKING:
    from backend.realization.camera_context import CameraContext


class OBSConnectionState:
    DISCONNECTED = "DISCONNECTED"
    CONNECTING = "CONNECTING"
    CONNECTED = "CONNECTED"
    ERROR = "ERROR"


class OBSClient:
    """
    Async OBS WebSocket client.

    Uses obs-websocket-py under the hood but wraps all calls in
    asyncio.to_thread() to avoid blocking the event loop.
    """

    def __init__(
        self,
        url: str = "ws://localhost:4455",
        password: str = "SECRET",
        on_state_change: Optional[Callable] = None,
    ) -> None:
        self._url = url
        self._password = password
        self._ws: Optional[obsws] = None
        self._state = OBSConnectionState.DISCONNECTED
        self._on_state_change = on_state_change
        self._reconnect_interval = 5.0
        self._scenes: List[str] = []
        self._current_program: Optional[str] = None
        self._current_preview: Optional[str] = None
        self._scene_snapshot_cache: Dict[str, tuple[float, Optional[str]]] = {}
        self._loop: Optional[asyncio.AbstractEventLoop] = None

    @property
    def state(self) -> str:
        return self._state

    @property
    def is_connected(self) -> bool:
        return self._state == OBSConnectionState.CONNECTED

    @property
    def current_program_scene(self) -> Optional[str]:
        return self._current_program

    @property
    def current_preview_scene(self) -> Optional[str]:
        return self._current_preview

    async def connect(self) -> None:
        self._set_state(OBSConnectionState.CONNECTING)
        try:
            self._loop = asyncio.get_running_loop()
            # Parse ws://host:port into components
            url = self._url.replace("ws://", "").replace("wss://", "")
            host, port = url.rsplit(":", 1) if ":" in url else (url, "4455")

            self._ws = obsws(host, int(port), self._password)
            self._ws.register(self._on_event)
            await asyncio.to_thread(self._ws.connect)

            self._set_state(OBSConnectionState.CONNECTED)
            log.info("obs_client.connected", url=self._url)

            # Cache scene list
            await self.refresh_scenes()
            await self._refresh_current_scenes()

        except Exception as e:
            self._set_state(OBSConnectionState.ERROR)
            log.error("obs_client.connect_failed", error=str(e))
            raise

    async def disconnect(self) -> None:
        if self._ws:
            try:
                await asyncio.to_thread(self._ws.disconnect)
            except Exception:
                pass
        self._ws = None
        self._scene_snapshot_cache.clear()
        self._set_state(OBSConnectionState.DISCONNECTED)
        log.info("obs_client.disconnected")

    async def set_program_scene(self, scene_name: str) -> None:
        """Switch the program output to the named scene."""
        if not self.is_connected:
            raise RuntimeError("OBS not connected")
        await asyncio.to_thread(
            self._ws.call,
            obs_requests.SetCurrentProgramScene(sceneName=scene_name),
        )
        self._current_program = scene_name
        log.info("obs_client.program_scene_set", scene=scene_name)

    async def set_preview_scene(self, scene_name: str) -> None:
        """Set the preview/studio monitor scene."""
        if not self.is_connected:
            raise RuntimeError("OBS not connected")
        await asyncio.to_thread(
            self._ws.call,
            obs_requests.SetCurrentPreviewScene(sceneName=scene_name),
        )
        self._current_preview = scene_name
        log.info("obs_client.preview_scene_set", scene=scene_name)

    async def trigger_transition(self, transition_name: Optional[str] = None) -> None:
        """Trigger a studio mode transition (preview → program)."""
        if not self.is_connected:
            raise RuntimeError("OBS not connected")
        if transition_name:
            await asyncio.to_thread(
                self._ws.call,
                obs_requests.SetCurrentSceneTransition(transitionName=transition_name),
            )
        await asyncio.to_thread(
            self._ws.call,
            obs_requests.TriggerStudioModeTransition(),
        )
        log.info("obs_client.transition_triggered", transition=transition_name)

    async def refresh_scenes(self) -> List[str]:
        """Fetch and cache available scene list."""
        if not self.is_connected:
            return []
        resp = await asyncio.to_thread(
            self._ws.call,
            obs_requests.GetSceneList(),
        )
        self._scenes = [s["sceneName"] for s in resp.getScenes()]
        log.debug("obs_client.scenes_refreshed", count=len(self._scenes))
        return self._scenes

    async def _refresh_current_scenes(self) -> None:
        if not self.is_connected or not self._ws:
            return
        try:
            resp = await asyncio.to_thread(
                self._ws.call,
                obs_requests.GetCurrentProgramScene(),
            )
            if hasattr(resp, "getSceneName"):
                self._current_program = resp.getSceneName()
            elif hasattr(resp, "datain"):
                self._current_program = (
                    resp.datain.get("currentProgramSceneName")
                    or resp.datain.get("sceneName")
                )
        except Exception as e:
            log.warning("obs_client.current_program_failed", error=str(e))
        try:
            resp = await asyncio.to_thread(
                self._ws.call,
                obs_requests.GetCurrentPreviewScene(),
            )
            if hasattr(resp, "getSceneName"):
                self._current_preview = resp.getSceneName()
            elif hasattr(resp, "datain"):
                self._current_preview = (
                    resp.datain.get("currentPreviewSceneName")
                    or resp.datain.get("sceneName")
                )
        except Exception as e:
            log.warning("obs_client.current_preview_failed", error=str(e))

    async def get_scene_snapshot(self, scene_name: str) -> Optional[str]:
        """Return base64 JPEG for a scene (no data: prefix)."""
        if not self.is_connected or not self._ws:
            return None
        resp = await asyncio.to_thread(
            self._ws.call,
            obs_requests.GetSourceScreenshot(
                sourceName=scene_name,
                imageFormat="jpg",
            ),
        )
        image_data: Optional[str] = None
        if hasattr(resp, "getImageData"):
            image_data = resp.getImageData()
        elif hasattr(resp, "datain"):
            image_data = resp.datain.get("imageData")
        if not image_data:
            return None
        if image_data.startswith("data:image"):
            return image_data.split(",", 1)[-1]
        return image_data

    async def get_scene_snapshot_cached(self, scene_name: str, ttl_s: float = 2.0) -> Optional[str]:
        if ttl_s <= 0:
            return await self.get_scene_snapshot(scene_name)
        now = time.monotonic()
        cached = self._scene_snapshot_cache.get(scene_name)
        if cached and (now - cached[0]) <= ttl_s:
            return cached[1]
        image_data = await self.get_scene_snapshot(scene_name)
        self._scene_snapshot_cache[scene_name] = (now, image_data)
        return image_data

    async def get_status(self) -> Dict[str, Any]:
        if self.is_connected:
            await self._refresh_current_scenes()
        return {
            "state": self._state,
            "url": self._url,
            "current_program": self._current_program,
            "current_preview": self._current_preview,
            "scenes": self._scenes,
        }

    def _set_state(self, state: str) -> None:
        self._state = state
        if self._on_state_change:
            asyncio.create_task(self._on_state_change(state))

    def _on_event(self, event: Any) -> None:
        """Receive events from OBS (scene changes, etc.)."""
        event_type = type(event).__name__
        scene_name = getattr(event, "sceneName", None) or getattr(event, "scene_name", None) or getattr(event, "datain", {}).get("sceneName") or getattr(event, "datain", {}).get("scene_name")
        if scene_name:
            # Update internal cache
            if event_type in {"CurrentProgramSceneChanged", "CurrentSceneChanged"}:
                self._current_program = scene_name
                global_context.program_scene_name = scene_name
                global_context.program_scene_since = time.monotonic()

                self._run_on_loop(self._handle_program_scene_changed(scene_name))

            elif event_type == "CurrentPreviewSceneChanged":
                self._current_preview = scene_name
                try:
                    match_ctx = self._resolve_camera_by_scene(scene_name)
                    global_context.preview_camera_id = match_ctx.camera_id if match_ctx else None
                    self._run_on_loop(self._broadcast_obs_sync(None, scene_name, preview_only=True))
                except Exception:
                    log.exception("obs_client.preview_scene_sync_failed")

        log.debug("obs_client.event", event_type=event_type)

    def _resolve_camera_by_scene(self, scene_name: str) -> Optional["CameraContext"]:
        # Find camera with matching explicit obs_scene_name first
        for ctx in subscriber_registry.get_all_contexts():
            if ctx.obs_scene_name and ctx.obs_scene_name == scene_name:
                return ctx

        # Fallback: search subscription scene options
        for ctx in subscriber_registry.get_all_contexts():
            for sub in ctx.subscriptions:
                for opt in sub.obs_scene_options:
                    if opt.scene_name == scene_name:
                        return ctx
        return None

    def _resolve_camera_id_by_scene_db(self, scene_name: str) -> Optional[str]:
        cameras = camera_registry.get_all()
        for camera in cameras:
            if (
                camera.enabled
                and camera.source_type == "obs_scene"
                and camera.source_url == scene_name
            ):
                return camera.id
        return None



    async def _handle_program_scene_changed(self, scene_name: str) -> None:
        """Map OBS program scene to an OBS-scene camera and update global context."""
        try:
            match_id = self._resolve_camera_id_by_scene_db(scene_name)
            if not match_id:
                return

            prev_cam = global_context.program_camera_id
            if prev_cam != match_id:
                if prev_cam:
                    prev_sub = subscriber_registry.get_subscriber(prev_cam)
                    if prev_sub:
                        prev_sub.context.mark_off_air()

                match_sub = subscriber_registry.get_subscriber(match_id)
                if match_sub:
                    match_sub.context.mark_on_air()

                global_context.program_camera_id = match_id
                global_context.program_since = time.monotonic()
                global_context.record_switch(SwitchRecord(
                    from_camera=prev_cam,
                    to_camera=match_id,
                    reason="obs_external_switch",
                    score=0.0,
                    event_type=None,
                ))

            await self._broadcast_obs_sync(match_id, scene_name)
        except Exception:
            log.exception("obs_client.program_scene_sync_failed")

    def _run_on_loop(self, coro: Coroutine[Any, Any, Any]) -> None:
        if self._loop and self._loop.is_running():
            asyncio.run_coroutine_threadsafe(coro, self._loop)
        else:
            asyncio.create_task(coro)

    async def _broadcast_obs_sync(
        self,
        program_camera_id: Optional[str],
        scene_name: str,
        preview_only: bool = False,
    ) -> None:
        try:
            await ws_manager.broadcast({
                "type": "obs_state",
                "data": {
                    "state": self._state,
                    "url": self._url,
                    "current_program": self._current_program,
                    "current_preview": self._current_preview,
                    "scenes": self._scenes,
                },
                "ts": time.time(),
            })

            if not preview_only and program_camera_id:
                await ws_manager.broadcast({
                    "type": "program_switch",
                    "data": {"camera_id": program_camera_id, "scene": scene_name},
                })

            # Push updated global context and camera scores so UI reflects ON AIR immediately
            await ws_manager.broadcast({
                "type": "global_context",
                "data": global_context.to_dict(),
            })

            camera_scores = [ctx.to_dict() for ctx in subscriber_registry.get_all_contexts()]
            await ws_manager.broadcast({
                "type": "camera_scores",
                "data": camera_scores,
                "ts": time.time(),
            })
        except Exception:
            log.exception("obs_client.broadcast_sync_failed")


# ── Singleton with lazy init ──────────────────────────────────────────────────
_obs_client: Optional[OBSClient] = None


def get_obs_client() -> OBSClient:
    global _obs_client
    from backend.core.settings import get_settings
    s = get_settings()
    if _obs_client is None:
        log.info("obs_client.initializing", url=s.obs_websocket_url, password=s.obs_websocket_password)
        _obs_client = OBSClient(url=s.obs_websocket_url, password=s.obs_websocket_password)
    return _obs_client
