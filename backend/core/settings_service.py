"""
Settings Service — Manages application settings persistence and caching.

Provides a layer above Pydantic Settings to allow runtime configuration changes
via the database while maintaining backward compatibility with environment variables.
"""

from __future__ import annotations

import json
from typing import Any, Dict, Optional

import structlog

log = structlog.get_logger(__name__)

# In-memory cache of settings
_settings_cache: Dict[str, Any] = {}


class SettingsService:
    """
    Manages application settings with DB persistence and in-memory caching.
    
    Usage:
        service = SettingsService(db_session)
        await service.load_from_db()
        value = service.get("obs_websocket_url", default="ws://localhost:4455")
        await service.set("obs_websocket_url", "ws://obs:4455")
    """

    def __init__(self, db_session=None):
        self.db = db_session
        self.cache: Dict[str, Any] = {}

    async def load_from_db(self) -> None:
        """Load all settings from database into cache."""
        if not self.db:
            log.warning("settings_service.no_db")
            return

        try:
            from backend.models import ApplicationSetting
            from sqlalchemy import select

            result = await self.db.execute(select(ApplicationSetting))
            settings = result.scalars().all()

            for setting in settings:
                self.cache[setting.key] = self._cast_value(setting.value, setting.value_type)

            log.info("settings_service.loaded_from_db", count=len(settings))
        except Exception as e:
            log.error("settings_service.load_failed", error=str(e))

    async def initialize_defaults(self, defaults: Dict[str, tuple[Any, str, str]]) -> None:
        """
        Initialize settings table with defaults if empty.
        
        Args:
            defaults: Dict of {key: (value, type, description)}
                     Example: {
                         "obs_websocket_url": ("ws://localhost:4455", "string", "OBS WebSocket endpoint"),
                         "decision_cycle_ms": (50, "int", "Decision engine cycle time")
                     }
        """
        if not self.db:
            return

        try:
            from backend.models import ApplicationSetting
            from sqlalchemy import select

            # Check if any settings exist
            result = await self.db.execute(select(ApplicationSetting))
            existing = result.scalars().first()

            if existing is not None:
                log.info("settings_service.already_initialized")
                return

            # Create defaults
            for key, (value, vtype, description) in defaults.items():
                setting = ApplicationSetting(
                    key=key,
                    value=str(value),
                    value_type=vtype,
                    description=description,
                )
                self.db.add(setting)
                self.cache[key] = value

            await self.db.commit()
            log.info("settings_service.initialized_defaults", count=len(defaults))
        except Exception as e:
            log.error("settings_service.initialize_failed", error=str(e))

    def get(self, key: str, default: Any = None) -> Any:
        """Get setting value from cache (non-async)."""
        return self.cache.get(key, default)

    async def set(self, key: str, value: Any, value_type: str = "string", description: str = "") -> bool:
        """
        Set a setting value in DB and cache.
        
        Returns:
            True if successful, False otherwise
        """
        if not self.db:
            log.warning("settings_service.no_db_for_set", key=key)
            return False

        try:
            from backend.models import ApplicationSetting
            from sqlalchemy import select

            # Update or insert
            result = await self.db.execute(select(ApplicationSetting).where(ApplicationSetting.key == key))
            setting = result.scalar_one_or_none()

            if setting:
                setting.value = str(value)
                setting.value_type = value_type
                if description:
                    setting.description = description
            else:
                setting = ApplicationSetting(
                    key=key,
                    value=str(value),
                    value_type=value_type,
                    description=description,
                )
                self.db.add(setting)

            await self.db.commit()

            # Update cache with proper type
            self.cache[key] = self._cast_value(str(value), value_type)
            log.info("settings_service.updated", key=key, value_type=value_type)
            return True

        except Exception as e:
            log.error("settings_service.set_failed", key=key, error=str(e))
            return False

    async def bulk_update(self, updates: Dict[str, tuple[Any, str]]) -> bool:
        """
        Update multiple settings at once.
        
        Args:
            updates: Dict of {key: (value, type)}
        """
        if not self.db:
            return False

        try:
            from backend.models import ApplicationSetting
            from sqlalchemy import select

            for key, (value, vtype) in updates.items():
                result = await self.db.execute(select(ApplicationSetting).where(ApplicationSetting.key == key))
                setting = result.scalar_one_or_none()

                if setting:
                    setting.value = str(value)
                    setting.value_type = vtype
                else:
                    setting = ApplicationSetting(key=key, value=str(value), value_type=vtype)
                    self.db.add(setting)

                self.cache[key] = self._cast_value(str(value), vtype)

            await self.db.commit()
            log.info("settings_service.bulk_updated", count=len(updates))
            return True

        except Exception as e:
            log.error("settings_service.bulk_update_failed", error=str(e))
            return False

    def get_all(self) -> Dict[str, Any]:
        """Get all settings from cache."""
        return dict(self.cache)

    @staticmethod
    def _cast_value(value: str, value_type: str) -> Any:
        """Cast string value to appropriate type."""
        try:
            if value_type == "int":
                return int(value)
            elif value_type == "float":
                return float(value)
            elif value_type == "bool":
                return value.lower() in ("true", "1", "yes", "on")
            elif value_type == "list":
                return json.loads(value)
            elif value_type == "json":
                return json.loads(value)
            else:  # string
                return value
        except (ValueError, json.JSONDecodeError):
            log.warning("settings_service.cast_failed", value=value, type=value_type)
            return value


# Global service instance
_service: Optional[SettingsService] = None


def get_settings_service() -> SettingsService:
    """Get or create global settings service."""
    global _service
    if _service is None:
        _service = SettingsService()
    return _service


def set_settings_service(service: SettingsService) -> None:
    """Set global settings service (called during app initialization)."""
    global _service
    _service = service
