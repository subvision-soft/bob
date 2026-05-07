"""
Cameras API — CRUD + subscription management + live context query.
"""

from __future__ import annotations

from typing import List

import structlog
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from backend.database import get_db
from backend.models import Camera, CameraSubscriptionModel
from backend.realization.camera_context import CameraContext, CameraSubscription, ReactionMode
from backend.realization.camera_subscriber import subscriber_registry
from backend.schemas import CameraCreate, CameraResponse, CameraUpdate

log = structlog.get_logger(__name__)
router = APIRouter()


def _model_to_response(camera: Camera) -> CameraResponse:
    return CameraResponse(
        id=camera.id,
        name=camera.name,
        label=camera.label,
        source_type=camera.source_type,
        source_url=camera.source_url,
        obs_scene_name=camera.obs_scene_name,
        enabled=camera.enabled,
        is_active=camera.is_active,
        subscriptions=[
            {
                "event_type": s.event_type,
                "mode": s.mode,
                "priority": s.priority,
                "duration_ms": s.duration_ms,
                "cooldown_ms": s.cooldown_ms,
                "delay_ms": s.delay_ms,
                "enabled": s.enabled,
                "conditions": s.conditions,
            }
            for s in camera.subscriptions
        ],
    )


async def _register_camera_subscriber(camera: Camera) -> None:
    """Build CameraContext from DB model and register in subscriber registry."""
    subs = [
        CameraSubscription(
            event_type=s.event_type,
            mode=ReactionMode(s.mode),
            priority=s.priority,
            duration_ms=s.duration_ms,
            cooldown_ms=s.cooldown_ms,
            delay_ms=s.delay_ms,
            enabled=s.enabled,
        )
        for s in camera.subscriptions
    ]
    ctx = CameraContext(camera_id=camera.id, subscriptions=subs)
    await subscriber_registry.register(ctx)


@router.get("/", response_model=List[CameraResponse])
async def list_cameras(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Camera).where(Camera.enabled == True))
    cameras = result.scalars().all()
    return [_model_to_response(c) for c in cameras]


@router.post("/", response_model=CameraResponse, status_code=status.HTTP_201_CREATED)
async def create_camera(payload: CameraCreate, db: AsyncSession = Depends(get_db)):
    camera = Camera(
        name=payload.name,
        label=payload.label,
        source_type=payload.source_type,
        source_url=payload.source_url,
        obs_scene_name=payload.obs_scene_name,
        enabled=payload.enabled,
    )
    db.add(camera)
    await db.flush()

    for sub in payload.subscriptions:
        db.add(CameraSubscriptionModel(
            camera_id=camera.id,
            event_type=sub.event_type,
            mode=sub.mode,
            priority=sub.priority,
            duration_ms=sub.duration_ms,
            cooldown_ms=sub.cooldown_ms,
            delay_ms=sub.delay_ms,
            enabled=sub.enabled,
            conditions=sub.conditions,
        ))

    await db.commit()
    await db.refresh(camera)

    # Register in live subscriber system
    await _register_camera_subscriber(camera)

    log.info("cameras.created", camera_id=camera.id, name=camera.name)
    return _model_to_response(camera)


@router.get("/{camera_id}", response_model=CameraResponse)
async def get_camera(camera_id: str, db: AsyncSession = Depends(get_db)):
    camera = await db.get(Camera, camera_id)
    if not camera:
        raise HTTPException(status_code=404, detail="Camera not found")
    return _model_to_response(camera)


@router.put("/{camera_id}", response_model=CameraResponse)
async def update_camera(
    camera_id: str,
    payload: CameraUpdate,
    db: AsyncSession = Depends(get_db),
):
    camera = await db.get(Camera, camera_id)
    if not camera:
        raise HTTPException(status_code=404, detail="Camera not found")

    if payload.name is not None:
        camera.name = payload.name
    if payload.label is not None:
        camera.label = payload.label
    if payload.source_type is not None:
        camera.source_type = payload.source_type
    if payload.source_url is not None:
        camera.source_url = payload.source_url
    if payload.obs_scene_name is not None:
        camera.obs_scene_name = payload.obs_scene_name
    if payload.enabled is not None:
        camera.enabled = payload.enabled

    if payload.subscriptions is not None:
        # Replace all subscriptions
        await db.execute(
            CameraSubscriptionModel.__table__.delete().where(
                CameraSubscriptionModel.camera_id == camera_id
            )
        )
        for sub in payload.subscriptions:
            db.add(CameraSubscriptionModel(
                camera_id=camera.id,
                event_type=sub.event_type,
                mode=sub.mode,
                priority=sub.priority,
                duration_ms=sub.duration_ms,
                cooldown_ms=sub.cooldown_ms,
                delay_ms=sub.delay_ms,
                enabled=sub.enabled,
                conditions=sub.conditions,
            ))

    await db.commit()
    await db.refresh(camera)

    # Re-register subscriber with new config
    await subscriber_registry.unregister(camera_id)
    if camera.enabled:
        await _register_camera_subscriber(camera)

    return _model_to_response(camera)


@router.delete("/{camera_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_camera(camera_id: str, db: AsyncSession = Depends(get_db)):
    camera = await db.get(Camera, camera_id)
    if not camera:
        raise HTTPException(status_code=404, detail="Camera not found")
    await subscriber_registry.unregister(camera_id)
    await db.delete(camera)
    await db.commit()


@router.get("/{camera_id}/context")
async def get_camera_context(camera_id: str):
    """Return live context (score, cooldown, state) for a camera."""
    sub = subscriber_registry.get_subscriber(camera_id)
    if not sub:
        raise HTTPException(status_code=404, detail="Camera not active in engine")
    return sub.context.to_dict()


@router.get("/live/scores")
async def get_all_scores():
    """Return live scores for all cameras — used by monitoring UI."""
    return [ctx.to_dict() for ctx in subscriber_registry.get_all_contexts()]
