"""
Subvision Studio — Backend Entry Point
FastAPI application factory with lifespan management for all background workers.
"""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from typing import AsyncGenerator

import structlog
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from prometheus_fastapi_instrumentator import Instrumentator

from backend.api import cameras, config, events, monitoring, obs, rules
from backend.core.settings import get_settings
from backend.database import init_db, migrate_subscription_scene_options
from backend.websocket.manager import ws_manager
from backend.workers.decision_worker import DecisionWorker
from backend.workers.event_poller_worker import EventPollerWorker
from backend.workers.snapshot_worker import SnapshotWorker
from backend.workers.video_ingest_worker import VideoIngestWorker

log = structlog.get_logger(__name__)
settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """
    Application lifespan: start all background workers on startup,
    cancel them cleanly on shutdown.
    """
    log.info("subvision_studio.starting", version="0.1.0")

    # ── Database ──────────────────────────────────────────────────────
    await init_db()
    await migrate_subscription_scene_options()

    # ── Background workers ────────────────────────────────────────────
    event_poller = EventPollerWorker()
    decision = DecisionWorker()
    video_ingest = VideoIngestWorker()
    snapshot = SnapshotWorker()

    tasks = [
        asyncio.create_task(event_poller.run(), name="event_poller"),
        asyncio.create_task(decision.run(), name="decision_engine"),
        asyncio.create_task(video_ingest.run(), name="video_ingest"),
        asyncio.create_task(snapshot.run(), name="snapshot"),
    ]

    log.info("subvision_studio.workers_started", count=len(tasks))

    yield  # ── Application is running ──────────────────────────────────

    log.info("subvision_studio.shutting_down")
    for task in tasks:
        task.cancel()
    await asyncio.gather(*tasks, return_exceptions=True)
    log.info("subvision_studio.stopped")


def create_app() -> FastAPI:
    app = FastAPI(
        title="Subvision Studio",
        description="Automated broadcast direction for underwater shooting competitions",
        version="0.1.0",
        lifespan=lifespan,
    )

    # ── CORS ──────────────────────────────────────────────────────────
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # ── Prometheus metrics ────────────────────────────────────────────
    Instrumentator().instrument(app).expose(app)

    # ── REST routers ──────────────────────────────────────────────────
    app.include_router(cameras.router, prefix="/api/cameras", tags=["cameras"])
    app.include_router(rules.router, prefix="/api/rules", tags=["rules"])
    app.include_router(events.router, prefix="/api/events", tags=["events"])
    app.include_router(obs.router, prefix="/api/obs", tags=["obs"])
    app.include_router(config.router, prefix="/api/config", tags=["config"])
    app.include_router(monitoring.router, prefix="/api/monitoring", tags=["monitoring"])

    # ── WebSocket endpoint ────────────────────────────────────────────
    from backend.api.websocket import router as ws_router

    app.include_router(ws_router)

    return app


app = create_app()
