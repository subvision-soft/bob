"""
Decision Worker — Drives the Realization Decision Engine loop.
Wires up OBS client and WebSocket broadcast callback on startup.
"""

from __future__ import annotations

import structlog

from backend.obs.client import get_obs_client
from backend.realization.decision_engine import decision_engine
from backend.websocket.manager import ws_manager

log = structlog.get_logger(__name__)


class DecisionWorker:
    async def run(self) -> None:
        # Wire dependencies
        decision_engine.set_obs_client(get_obs_client())
        decision_engine.set_ws_broadcast(ws_manager.broadcast)

        log.info("decision_worker.starting")
        await decision_engine.run()
