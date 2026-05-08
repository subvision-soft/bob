"""
SQLAlchemy Models — Subvision Studio

Uses SQLAlchemy 2.0 declarative style with async support.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


def _uuid() -> str:
    return str(uuid.uuid4())


# ── Camera ────────────────────────────────────────────────────────────────────

class Camera(Base):
    __tablename__ = "cameras"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    label: Mapped[str] = mapped_column(String(64), nullable=False)  # display label in UI

    # Source configuration
    source_type: Mapped[str] = mapped_column(String(32), default="rtsp")  # rtsp|ndi|webcam|obs_scene
    source_url: Mapped[Optional[str]] = mapped_column(String(512))
    obs_scene_name: Mapped[Optional[str]] = mapped_column(String(256))

    # Status
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=False)  # on air

    # Metadata
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())

    # Relationships
    subscriptions: Mapped[List["CameraSubscriptionModel"]] = relationship(
        back_populates="camera", cascade="all, delete-orphan"
    )
    obs_scene_options: Mapped[List["CameraObsSceneOption"]] = relationship(
        back_populates="camera", cascade="all, delete-orphan"
    )


class CameraSubscriptionModel(Base):
    __tablename__ = "camera_subscriptions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    camera_id: Mapped[str] = mapped_column(ForeignKey("cameras.id"), nullable=False)

    event_type: Mapped[str] = mapped_column(String(64), nullable=False)
    mode: Mapped[str] = mapped_column(String(32), default="INFORM_ONLY")
    priority: Mapped[float] = mapped_column(Float, default=50.0)
    duration_ms: Mapped[int] = mapped_column(Integer, default=3000)
    cooldown_ms: Mapped[int] = mapped_column(Integer, default=0)
    delay_ms: Mapped[int] = mapped_column(Integer, default=0)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    conditions: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON)

    camera: Mapped["Camera"] = relationship(back_populates="subscriptions")
    obs_scene_options: Mapped[List["CameraSubscriptionSceneOption"]] = relationship(
        back_populates="subscription", cascade="all, delete-orphan"
    )


class CameraObsSceneOption(Base):
    __tablename__ = "camera_obs_scene_options"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    camera_id: Mapped[str] = mapped_column(ForeignKey("cameras.id"), nullable=False)

    scene_name: Mapped[str] = mapped_column(String(256), nullable=False)
    weight: Mapped[float] = mapped_column(Float, default=1.0)

    camera: Mapped["Camera"] = relationship(back_populates="obs_scene_options")


class CameraSubscriptionSceneOption(Base):
    __tablename__ = "camera_subscription_scene_options"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    subscription_id: Mapped[str] = mapped_column(
        ForeignKey("camera_subscriptions.id"),
        nullable=False,
    )

    scene_name: Mapped[str] = mapped_column(String(256), nullable=False)
    weight: Mapped[float] = mapped_column(Float, default=1.0)

    subscription: Mapped["CameraSubscriptionModel"] = relationship(
        back_populates="obs_scene_options"
    )


# ── Competition Rules ─────────────────────────────────────────────────────────

class RuleProfile(Base):
    __tablename__ = "rule_profiles"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    name: Mapped[str] = mapped_column(String(128), nullable=False, unique=True)
    description: Mapped[Optional[str]] = mapped_column(Text)
    is_active: Mapped[bool] = mapped_column(Boolean, default=False)
    parent_profile_id: Mapped[Optional[str]] = mapped_column(ForeignKey("rule_profiles.id"))
    config: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON)  # global engine config overrides

    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())


# ── Event Log ─────────────────────────────────────────────────────────────────

class EventLog(Base):
    __tablename__ = "event_logs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    external_id: Mapped[Optional[str]] = mapped_column(String(128))
    event_type: Mapped[str] = mapped_column(String(64), nullable=False)
    severity: Mapped[str] = mapped_column(String(16), default="MEDIUM")

    competition_id: Mapped[Optional[str]] = mapped_column(String(128))
    athlete_id: Mapped[Optional[str]] = mapped_column(String(128))
    lane: Mapped[Optional[int]] = mapped_column(Integer)

    frame_id: Mapped[Optional[int]] = mapped_column(Integer)
    frame_timestamp: Mapped[Optional[float]] = mapped_column(Float)

    raw_payload: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON)
    received_at: Mapped[float] = mapped_column(Float, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


# ── Switch Log ────────────────────────────────────────────────────────────────

class SwitchLog(Base):
    __tablename__ = "switch_logs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    from_camera_id: Mapped[Optional[str]] = mapped_column(String(128))
    to_camera_id: Mapped[str] = mapped_column(String(128), nullable=False)
    trigger_event_type: Mapped[Optional[str]] = mapped_column(String(64))
    score: Mapped[float] = mapped_column(Float, default=0.0)
    reason: Mapped[str] = mapped_column(String(256), default="")
    wall_time: Mapped[float] = mapped_column(Float, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
