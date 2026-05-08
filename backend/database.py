"""
Async SQLAlchemy database setup.
"""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy import select
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
                    ))
                    added += 1
        if added:
            await session.commit()


async def get_db() -> AsyncSession:
    async with AsyncSessionLocal() as session:
        yield session


def get_db_session() -> AsyncSession:
    """Get a database session instance (not a generator)."""
    return AsyncSessionLocal()
