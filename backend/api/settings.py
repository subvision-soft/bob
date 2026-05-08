"""
Settings API — Endpoints for managing application settings.
"""

from __future__ import annotations

from typing import Any, Dict, Optional

import structlog
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from backend.core.settings_service import get_settings_service

log = structlog.get_logger(__name__)
router = APIRouter()


class SettingUpdatePayload(BaseModel):
    """Request body for setting update."""
    value: str
    value_type: str = "string"
    description: Optional[str] = None


@router.get("/settings")
async def get_settings():
    """Get all application settings."""
    service = get_settings_service()
    settings = service.get_all()
    return {
        "status": "ok",
        "settings": settings,
    }


@router.get("/settings/{key}")
async def get_setting(key: str):
    """Get a specific setting by key."""
    service = get_settings_service()
    value = service.get(key)

    if value is None:
        raise HTTPException(status_code=404, detail=f"Setting '{key}' not found")

    return {
        "key": key,
        "value": value,
    }


@router.put("/settings/{key}")
async def update_setting(key: str, payload: SettingUpdatePayload):
    """
    Update a single setting.
    
    Payload:
    {
        "value": "new_value",
        "value_type": "string|int|float|bool|json",
        "description": "optional description"
    }
    """
    service = get_settings_service()

    success = await service.set(key, payload.value, payload.value_type, payload.description or "")

    if not success:
        raise HTTPException(status_code=500, detail="Failed to update setting")

    return {
        "status": "updated",
        "key": key,
        "value": service.get(key),
    }


@router.put("/settings")
async def update_settings(payload: Dict[str, Dict[str, Any]]):
    """
    Bulk update multiple settings.
    
    Payload:
    {
        "setting_key_1": {
            "value": "new_value",
            "value_type": "string"
        },
        "setting_key_2": {
            "value": 100,
            "value_type": "int"
        }
    }
    """
    service = get_settings_service()
    updates = {}

    for key, setting_data in payload.items():
        value = setting_data.get("value")
        value_type = setting_data.get("value_type", "string")

        if value is None:
            raise HTTPException(status_code=400, detail=f"'value' required for setting '{key}'")

        updates[key] = (value, value_type)

    success = await service.bulk_update(updates)

    if not success:
        raise HTTPException(status_code=500, detail="Failed to update settings")

    return {
        "status": "updated",
        "count": len(updates),
        "settings": service.get_all(),
    }
