"""
OBS API — Connect/disconnect, scene control, status.
"""

from __future__ import annotations

import structlog
from fastapi import APIRouter, HTTPException

from backend.obs.client import get_obs_client
from backend.schemas import OBSConnectRequest, OBSSceneSwitchRequest, OBSStatusResponse

log = structlog.get_logger(__name__)
router = APIRouter()


@router.get("/status", response_model=OBSStatusResponse)
async def obs_status():
    client = get_obs_client()
    return await client.get_status()


@router.post("/connect", status_code=200)
async def obs_connect(payload: OBSConnectRequest):
    try:
        # Create a new OBS client with the provided credentials
        from backend.obs.client import OBSClient, _obs_client
        import backend.obs.client as obs_module
        
        client = OBSClient(url=payload.url, password=payload.password)
        await client.connect()
        
        # Replace the global client with the new connected one
        obs_module._obs_client = client
        
        return {"status": "connected"}
    except Exception as e:
        raise HTTPException(status_code=503, detail=str(e))


@router.post("/disconnect", status_code=200)
async def obs_disconnect():
    client = get_obs_client()
    await client.disconnect()
    return {"status": "disconnected"}


@router.post("/scene", status_code=200)
async def set_scene(payload: OBSSceneSwitchRequest):
    client = get_obs_client()
    if not client.is_connected:
        raise HTTPException(status_code=503, detail="OBS not connected")
    if payload.target == "program":
        await client.set_program_scene(payload.scene_name)
    else:
        await client.set_preview_scene(payload.scene_name)
    return {"scene": payload.scene_name, "target": payload.target}


@router.get("/scenes")
async def get_scenes():
    client = get_obs_client()
    if not client.is_connected:
        raise HTTPException(status_code=503, detail="OBS not connected")
    return await client.refresh_scenes()
