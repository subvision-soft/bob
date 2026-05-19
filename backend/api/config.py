"""
Config API — Import/export JSON configuration bundles.
"""

from __future__ import annotations

import json
from typing import Any, Dict

from fastapi import APIRouter, HTTPException, UploadFile
from fastapi.responses import JSONResponse
from sqlalchemy import select

from backend.database import AsyncSessionLocal
from backend.models import Camera, CameraSubscriptionModel, RuleProfile
from sqlalchemy.orm import selectinload

router = APIRouter()


@router.get("/export")
async def export_config():
    async with AsyncSessionLocal() as db:
        cameras_res = await db.execute(
            select(Camera).options(
                selectinload(Camera.subscriptions).selectinload(CameraSubscriptionModel.obs_scene_options)
            )
        )
        cameras = cameras_res.scalars().all()

        profiles_res = await db.execute(select(RuleProfile))
        profiles = profiles_res.scalars().all()

    return {
        "version": "1.0",
        "cameras": [
            {
                "id": c.id,
                "name": c.name,
                "label": c.label,
                "source_type": c.source_type,
                "source_url": c.source_url,
                "obs_scene_name": c.obs_scene_name,
                "obs_scene_weight": c.obs_scene_weight,
                "obs_scene_max_display_ms": c.obs_scene_max_display_ms,
                "enabled": c.enabled,
                "subscriptions": [
                    {
                        "event_type": s.event_type,
                        "mode": s.mode,
                        "priority": s.priority,
                        "duration_ms": s.duration_ms,
                        "cooldown_ms": s.cooldown_ms,
                        "delay_ms": s.delay_ms,
                        "enabled": s.enabled,
                        "obs_scene_options": [
                            {
                                "scene_name": o.scene_name,
                                "weight": o.weight,
                                "max_display_ms": o.max_display_ms,
                            }
                            for o in s.obs_scene_options
                        ],
                    }
                    for s in c.subscriptions
                ],
            }
            for c in cameras
        ],
        "profiles": [
            {
                "id": p.id,
                "name": p.name,
                "description": p.description,
                "is_active": p.is_active,
                "config": p.config,
            }
            for p in profiles
        ],
    }
