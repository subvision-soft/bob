"""
WebSocket Connection Manager — Real-time broadcast to Angular frontend.

Message types (discriminated union):
  - camera_scores     → per-camera live scoring snapshot
  - event_received    → new competition event
  - program_switch    → camera went on air
  - decision_trace    → full decision debug payload
  - obs_state         → OBS connection + scene state
  - stream_health     → video feed FPS/latency stats
  - log               → structured log entry
  - global_context    → global competition context
"""

from __future__ import annotations

import asyncio
import json
import time
from typing import Any, Dict, Set

import structlog
from fastapi import WebSocket, WebSocketDisconnect

log = structlog.get_logger(__name__)


class WebSocketManager:
    """
    Manages all active WebSocket connections and broadcasts messages to them.
    Non-blocking: uses asyncio.gather with return_exceptions=True.
    """

    def __init__(self) -> None:
        self._connections: Set[WebSocket] = set()
        self._lock = asyncio.Lock()
        self._stats = {"connections": 0, "messages_sent": 0, "errors": 0}

    async def connect(self, ws: WebSocket) -> None:
        await ws.accept()
        async with self._lock:
            self._connections.add(ws)
            self._stats["connections"] += 1
        log.info("ws_manager.client_connected", total=len(self._connections))

        # Send current state immediately on connect
        await self._send_initial_state(ws)

    async def disconnect(self, ws: WebSocket) -> None:
        async with self._lock:
            self._connections.discard(ws)
        log.info("ws_manager.client_disconnected", total=len(self._connections))

    async def broadcast(self, message: Dict[str, Any]) -> None:
        """Fan-out message to all connected clients."""
        if not self._connections:
            return

        payload = json.dumps(message)
        async with self._lock:
            connections = set(self._connections)

        results = await asyncio.gather(
            *[self._send(ws, payload) for ws in connections],
            return_exceptions=True,
        )

        # Clean up dead connections
        dead = [
            ws
            for ws, result in zip(connections, results)
            if isinstance(result, Exception)
        ]
        if dead:
            async with self._lock:
                for ws in dead:
                    self._connections.discard(ws)
                    self._stats["errors"] += 1

        self._stats["messages_sent"] += len(connections) - len(dead)

    async def _send(self, ws: WebSocket, payload: str) -> None:
        await ws.send_text(payload)

    async def _send_initial_state(self, ws: WebSocket) -> None:
        """Send the full current state to a newly connected client."""
        from backend.core.context_manager import global_context
        from backend.realization.camera_subscriber import subscriber_registry

        try:
            # Global context
            await self._send(ws, json.dumps({
                "type": "global_context",
                "data": global_context.to_dict(),
            }))

            # Camera contexts
            camera_scores = [
                ctx.to_dict() for ctx in subscriber_registry.get_all_contexts()
            ]
            await self._send(ws, json.dumps({
                "type": "camera_scores",
                "data": camera_scores,
                "ts": time.time(),
            }))
        except Exception as e:
            log.warning("ws_manager.initial_state_failed", error=str(e))

    @property
    def connection_count(self) -> int:
        return len(self._connections)

    def stats(self) -> dict:
        return {**self._stats, "active_connections": len(self._connections)}


# ── Singleton ─────────────────────────────────────────────────────────────────
ws_manager = WebSocketManager()
