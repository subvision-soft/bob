"""
Pydantic v2 Schemas — Request/Response DTOs for all API endpoints.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field, field_validator


# ── Camera Schemas ────────────────────────────────────────────────────────────

class CameraSubscriptionSchema(BaseModel):
    event_type: str
    mode: str = "INFORM_ONLY"
    priority: float = Field(50.0, ge=0, le=100)
    duration_ms: int = Field(3000, ge=100)
    cooldown_ms: int = Field(0, ge=0)
    delay_ms: int = Field(0, ge=0)
    enabled: bool = True
    conditions: Optional[Dict[str, Any]] = None
    obs_scene_options: List["CameraObsSceneOptionSchema"] = []


class CameraObsSceneOptionSchema(BaseModel):
    scene_name: str = Field(..., min_length=1, max_length=256)
    weight: float = Field(1.0, gt=0)


class CameraCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=128)
    label: str = Field(..., min_length=1, max_length=64)
    source_type: str = "rtsp"
    source_url: Optional[str] = None
    obs_scene_name: Optional[str] = None
    enabled: bool = True
    subscriptions: List[CameraSubscriptionSchema] = []

    @field_validator("source_type")
    @classmethod
    def validate_source_type(cls, v: str) -> str:
        valid = {"rtsp", "ndi", "webcam", "obs_scene", "mock"}
        if v not in valid:
            raise ValueError(f"source_type must be one of {valid}")
        return v


class CameraUpdate(BaseModel):
    name: Optional[str] = None
    label: Optional[str] = None
    source_type: Optional[str] = None
    source_url: Optional[str] = None
    obs_scene_name: Optional[str] = None
    enabled: Optional[bool] = None
    subscriptions: Optional[List[CameraSubscriptionSchema]] = None


class CameraResponse(BaseModel):
    id: str
    name: str
    label: str
    source_type: str
    source_url: Optional[str]
    obs_scene_name: Optional[str]
    enabled: bool
    is_active: bool
    subscriptions: List[CameraSubscriptionSchema]

    model_config = {"from_attributes": True}


# ── Rule Profile Schemas ──────────────────────────────────────────────────────

class RuleProfileCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=128)
    description: Optional[str] = None
    parent_profile_id: Optional[str] = None
    config: Optional[Dict[str, Any]] = None


class RuleProfileResponse(BaseModel):
    id: str
    name: str
    description: Optional[str]
    is_active: bool
    parent_profile_id: Optional[str]
    config: Optional[Dict[str, Any]]

    model_config = {"from_attributes": True}


# ── Event Schemas ─────────────────────────────────────────────────────────────

class EventSimulateRequest(BaseModel):
    """Used by the UI event simulator to inject test events."""
    event_type: str
    competition_id: Optional[str] = None
    athlete_id: Optional[str] = None
    lane: Optional[int] = None
    extra: Optional[Dict[str, Any]] = None


class EventLogResponse(BaseModel):
    id: str
    event_type: str
    severity: str
    competition_id: Optional[str]
    athlete_id: Optional[str]
    lane: Optional[int]
    frame_id: Optional[int]
    received_at: float

    model_config = {"from_attributes": True}


# ── OBS Schemas ───────────────────────────────────────────────────────────────

class OBSConnectRequest(BaseModel):
    url: str = "ws://localhost:4455"
    password: str = "SECRET"


class OBSSceneSwitchRequest(BaseModel):
    scene_name: str
    target: str = "program"  # "program" | "preview"


class OBSStatusResponse(BaseModel):
    state: str
    url: str
    current_program: Optional[str]
    current_preview: Optional[str]
    scenes: List[str]


# ── Config Schemas ────────────────────────────────────────────────────────────

class ConfigExportResponse(BaseModel):
    version: str = "1.0"
    cameras: List[Dict[str, Any]]
    profiles: List[Dict[str, Any]]


class ConfigImportRequest(BaseModel):
    version: str
    cameras: List[Dict[str, Any]]
    profiles: List[Dict[str, Any]]
    overwrite: bool = False


# ── WebSocket Message Schemas ─────────────────────────────────────────────────

class WSMessage(BaseModel):
    """Base WebSocket message envelope."""
    type: str
    data: Any
    ts: float = Field(default_factory=__import__("time").time)


# ── Monitoring ────────────────────────────────────────────────────────────────

class HealthResponse(BaseModel):
    status: str
    version: str
    uptime_s: float
    ws_connections: int
    event_engine_stats: Dict[str, int]
    decision_engine_active: bool
