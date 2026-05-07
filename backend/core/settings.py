"""
Subvision Studio — Application Settings
Pydantic-based settings with environment variable override.
"""

from __future__ import annotations

from functools import lru_cache
from typing import List

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="SVS_",
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )

    # ── Application ───────────────────────────────────────────────────
    app_name: str = "Subvision Studio"
    debug: bool = False
    log_level: str = "INFO"

    # ── Server ────────────────────────────────────────────────────────
    host: str = "0.0.0.0"
    port: int = 8000
    cors_origins: List[str] = Field(default=["http://localhost:4200", "http://localhost:80"])

    # ── Database ──────────────────────────────────────────────────────
    database_url: str = "sqlite+aiosqlite:///./subvision.db"

    # ── External Competition Event API ────────────────────────────────
    external_api_url: str = "http://localhost:9000/api"
    external_api_poll_interval_ms: int = 100  # poll every 100ms
    external_api_timeout_s: float = 5.0
    external_api_key: str = ""

    # ── OBS ───────────────────────────────────────────────────────────
    obs_websocket_url: str = "ws://localhost:4455"
    obs_websocket_password: str = ""
    obs_enabled: bool = True

    # ── Video / Streaming ─────────────────────────────────────────────
    video_snapshot_interval_ms: int = 500  # JPEG push interval
    video_hls_segment_duration: float = 0.5  # LL-HLS segment duration in seconds
    video_hls_output_dir: str = "./hls"
    ffmpeg_path: str = "ffmpeg"

    # ── Realization Engine ────────────────────────────────────────────
    decision_cycle_ms: int = 50        # decision evaluation frequency
    min_display_duration_ms: int = 2000  # minimum time on air
    default_cooldown_ms: int = 3000    # anti-zap global cooldown
    score_threshold_switch: float = 60.0  # minimum score for SWITCH_IF_HIGH_SCORE

    # ── Config profiles ───────────────────────────────────────────────
    config_dir: str = "./configs"
    default_profile: str = "default"

    @field_validator("cors_origins", mode="before")
    @classmethod
    def parse_cors(cls, v: str | List[str]) -> List[str]:
        if isinstance(v, str):
            return [origin.strip() for origin in v.split(",")]
        return v


@lru_cache
def get_settings() -> Settings:
    return Settings()
