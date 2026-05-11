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

from backend.api import cameras, config, events, monitoring, obs, rules, settings as settings_api
from backend.core.settings import get_settings
from backend.core.settings_service import SettingsService, set_settings_service
from backend.database import init_db, migrate_subscription_scene_options, get_db_session
from backend.websocket.manager import ws_manager
from backend.obs.client import get_obs_client
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

    # ── Settings Service ──────────────────────────────────────────────
    db_session = get_db_session()
    service = SettingsService(db_session)
    
    # Initialize default settings if table is empty
    default_settings = {
        "external_api_url": (settings.external_api_url, "string", "External competition API base URL"),
        "external_api_token_url": (settings.external_api_token_url, "string", "External competition API token URL"),
        "external_api_poll_interval_ms": (settings.external_api_poll_interval_ms, "int", "Poll interval for external API (ms)"),
        "obs_websocket_url": (settings.obs_websocket_url, "string", "OBS WebSocket URL"),
        "obs_websocket_password": (settings.obs_websocket_password, "string", "OBS WebSocket password"),
        "obs_enabled": (settings.obs_enabled, "bool", "Enable OBS integration"),
        "decision_cycle_ms": (settings.decision_cycle_ms, "int", "Decision engine cycle time (ms)"),
        "min_display_duration_ms": (settings.min_display_duration_ms, "int", "Minimum display duration before switch (ms)"),
        "default_cooldown_ms": (settings.default_cooldown_ms, "int", "Default post-switch cooldown (ms)"),
        "score_threshold_switch": (settings.score_threshold_switch, "float", "Score threshold for SWITCH_IF_HIGH_SCORE mode"),
        "video_snapshot_interval_ms": (settings.video_snapshot_interval_ms, "int", "Snapshot push interval (ms)"),
        "debug": (settings.debug, "bool", "Enable debug logging"),
    }
    
    await service.initialize_defaults(default_settings)
    await service.load_from_db()
    set_settings_service(service)

    # ── OBS Auto-Connect ──────────────────────────────────────────────
    if settings.obs_enabled:
        try:
            obs_client = get_obs_client()
            if not obs_client.is_connected:
                await obs_client.connect()
        except Exception as e:
            log.warning("obs_client.autoconnect_failed", error=str(e))

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
    app.include_router(settings_api.router, prefix="/api", tags=["settings"])

    # ── WebSocket endpoint ────────────────────────────────────────────
    from backend.api.websocket import router as ws_router

    app.include_router(ws_router)

    return app


app = create_app()
