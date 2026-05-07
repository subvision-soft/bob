"""
Rules API — Rule profile CRUD and active profile management.
"""

from __future__ import annotations

from typing import List

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from backend.database import get_db
from backend.models import RuleProfile
from backend.schemas import RuleProfileCreate, RuleProfileResponse

router = APIRouter()


@router.get("/profiles", response_model=List[RuleProfileResponse])
async def list_profiles(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(RuleProfile))
    return result.scalars().all()


@router.post("/profiles", response_model=RuleProfileResponse, status_code=status.HTTP_201_CREATED)
async def create_profile(payload: RuleProfileCreate, db: AsyncSession = Depends(get_db)):
    profile = RuleProfile(**payload.model_dump())
    db.add(profile)
    await db.commit()
    await db.refresh(profile)
    return profile


@router.get("/profiles/{profile_id}", response_model=RuleProfileResponse)
async def get_profile(profile_id: str, db: AsyncSession = Depends(get_db)):
    profile = await db.get(RuleProfile, profile_id)
    if not profile:
        raise HTTPException(status_code=404, detail="Profile not found")
    return profile


@router.post("/profiles/{profile_id}/activate", status_code=200)
async def activate_profile(profile_id: str, db: AsyncSession = Depends(get_db)):
    profile = await db.get(RuleProfile, profile_id)
    if not profile:
        raise HTTPException(status_code=404, detail="Profile not found")
    # Deactivate all others
    await db.execute(update(RuleProfile).values(is_active=False))
    profile.is_active = True
    await db.commit()
    return {"activated": profile_id}


@router.delete("/profiles/{profile_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_profile(profile_id: str, db: AsyncSession = Depends(get_db)):
    profile = await db.get(RuleProfile, profile_id)
    if not profile:
        raise HTTPException(status_code=404, detail="Profile not found")
    await db.delete(profile)
    await db.commit()
