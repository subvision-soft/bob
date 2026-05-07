"""
Monitoring API — Health, engine stats, system metrics.
"""

from __future__ import annotations

import time

from fastapi import APIRouter

from backend.core.context_manager import global_context
from backend.events.engine import event_engine
from backend.realization.camera_subscriber import subscriber_registry
from backend.websocket.manager import ws_manager

router = APIRouter()
_start_time = time.time()


@router.get("/health")
async def health():
    return {
        "status": "ok",
        "version": "0.1.0",
        "uptime_s": round(time.time() - _start_time, 1),
        "ws_connections": ws_manager.connection_count,
        "event_engine_stats": event_engine.stats,
        "cameras_registered": len(subscriber_registry.subscriber_ids),
        "decision_engine_active": True,
    }


@router.get("/context")
async def get_global_context():
    return global_context.to_dict()


@router.get("/switch-history")
async def get_switch_history(limit: int = 20):
    history = global_context.switch_history[-limit:]
    return [
        {
            "from_camera": r.from_camera,
            "to_camera": r.to_camera,
            "reason": r.reason,
            "score": round(r.score, 2),
            "event_type": r.event_type,
            "wall_time": r.wall_time,
        }
        for r in reversed(history)
    ]


@router.get("/bus-stats")
async def get_bus_stats():
    return {
        "stats": event_engine.stats,
        "queue_sizes": __import__("backend.core.event_bus", fromlist=["event_bus"]).event_bus.queue_sizes(),
        "ws_stats": ws_manager.stats(),
    }
