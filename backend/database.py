"""
Async SQLAlchemy database setup.
"""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy import select, text
from sqlalchemy.orm import selectinload

from backend.core.settings import get_settings
from backend.models import Base, Camera, CameraSubscriptionModel, CameraSubscriptionSceneOption

settings = get_settings()

engine = create_async_engine(
    settings.database_url,
    echo=settings.debug,
    pool_pre_ping=True,
)

AsyncSessionLocal = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


async def init_db() -> None:
    """Create all tables on startup (idempotent)."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def migrate_subscription_scene_options() -> None:
    """
    Migrate legacy camera-level OBS scene options to subscription-level options.
    Copies options to every subscription that doesn't already have its own list.
    """
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(Camera).options(
                selectinload(Camera.obs_scene_options),
                selectinload(Camera.subscriptions).selectinload(CameraSubscriptionModel.obs_scene_options),
            )
        )
        cameras = result.scalars().all()
        added = 0
        for camera in cameras:
            if not camera.obs_scene_options:
                continue
            for sub in camera.subscriptions:
                if sub.obs_scene_options:
                    continue
                for opt in camera.obs_scene_options:
                    session.add(CameraSubscriptionSceneOption(
                        subscription_id=sub.id,
                        scene_name=opt.scene_name,
                        weight=opt.weight,
                        max_display_ms=opt.max_display_ms,
                    ))
                    added += 1
        if added:
            await session.commit()


async def migrate_scene_option_max_display() -> None:
    """Ensure max_display_ms columns exist for scene option tables."""
    async with engine.begin() as conn:
        for table in ("camera_obs_scene_options", "camera_subscription_scene_options"):
            try:
                result = await conn.execute(text(f"PRAGMA table_info({table})"))
                columns = [row[1] for row in result.fetchall()]
                if "max_display_ms" in columns:
                    continue
            except Exception:
                # If PRAGMA fails (non-SQLite), attempt the ALTER directly.
                columns = []

            try:
                await conn.execute(text(
                    f"ALTER TABLE {table} ADD COLUMN max_display_ms INTEGER DEFAULT 0"
                ))
            except Exception:
                # Column likely already exists or database doesn't support ALTER in this way.
                pass


async def migrate_camera_obs_scene_fields() -> None:
    """Ensure obs_scene_weight and obs_scene_max_display_ms columns exist on cameras."""
    async with engine.begin() as conn:
        try:
            result = await conn.execute(text("PRAGMA table_info(cameras)"))
            columns = [row[1] for row in result.fetchall()]
        except Exception:
            columns = []

        if "obs_scene_weight" not in columns:
            try:
                await conn.execute(text(
                    "ALTER TABLE cameras ADD COLUMN obs_scene_weight FLOAT DEFAULT 1.0"
                ))
            except Exception:
                pass

        if "obs_scene_max_display_ms" not in columns:
            try:
                await conn.execute(text(
                    "ALTER TABLE cameras ADD COLUMN obs_scene_max_display_ms INTEGER DEFAULT 0"
                ))
            except Exception:
                pass


async def get_db() -> AsyncSession:
    async with AsyncSessionLocal() as session:
        yield session


def get_db_session() -> AsyncSession:
    """Get a database session instance (not a generator)."""
    return AsyncSessionLocal()
