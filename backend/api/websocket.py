"""
WebSocket API endpoint — single /ws endpoint for all real-time communication.
"""

from __future__ import annotations

import asyncio
import json

import structlog
from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from backend.core.context_manager import global_context
from backend.websocket.manager import ws_manager

log = structlog.get_logger(__name__)
router = APIRouter()


@router.websocket("/ws")
async def websocket_endpoint(ws: WebSocket):
    await ws_manager.connect(ws)
    try:
        while True:
            # Keep connection alive; handle inbound control messages
            raw = await ws.receive_text()
            try:
                msg = json.loads(raw)
                await _handle_client_message(msg, ws)
            except json.JSONDecodeError:
                pass
    except WebSocketDisconnect:
        log.info("ws.client_disconnected")
    finally:
        await ws_manager.disconnect(ws)


async def _handle_client_message(msg: dict, ws: WebSocket) -> None:
    """
    Handle inbound WebSocket messages from the Angular frontend.
    Currently supports:
      - ping → pong
      - simulate_event → inject event into bus
    """
    msg_type = msg.get("type")

    if msg_type == "ping":
        await ws.send_json({"type": "pong"})

    elif msg_type == "simulate_event":
        from backend.events.models import CompetitionEvent, EventType, EVENT_SEVERITY
        from backend.core.event_bus import event_bus
        raw_type = msg.get("event_type", "UNKNOWN")
        try:
            et = EventType(raw_type.upper())
        except ValueError:
            et = EventType.UNKNOWN
        event = CompetitionEvent(
            type=et,
            severity=EVENT_SEVERITY.get(et),
            raw_payload={"source": "ws_simulate", **msg},
        )
        await event_bus.publish(event)
        global_context.mark_event_activity()
        await ws_manager.broadcast_event_received(event)
        await ws.send_json({"type": "simulate_ack", "event_id": event.id})
