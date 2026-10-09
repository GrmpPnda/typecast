from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_admin
from app.db.engine import get_db
from app.models.profile import Profile
from app.repositories.sqlalchemy_repo import SQLAlchemyRepository
from app.schemas.profile import ProfileCreate, ProfileResponse, ProfileUpdate

router = APIRouter()

# Profiles are install-wide: any account may use them, only an administrator may
# change one, since deleting a profile changes every work that uses it.
ADMIN = [Depends(require_admin)]


def get_repo(db: AsyncSession = Depends(get_db)) -> SQLAlchemyRepository[Profile]:
    return SQLAlchemyRepository(db, Profile)


@router.get("/", response_model=list[ProfileResponse])
async def list_profiles(
    repo: SQLAlchemyRepository[Profile] = Depends(get_repo),
):
    return await repo.get_all()


@router.get("/{profile_id}", response_model=ProfileResponse)
async def get_profile(
    profile_id: uuid.UUID, repo: SQLAlchemyRepository[Profile] = Depends(get_repo)
):
    profile = await repo.get_by_id(profile_id)
    if profile is None:
        raise HTTPException(status_code=404, detail="Profile not found")
    return profile


@router.post("/", response_model=ProfileResponse, status_code=201, dependencies=ADMIN)
async def create_profile(
    data: ProfileCreate, repo: SQLAlchemyRepository[Profile] = Depends(get_repo)
):
    return await repo.create(**data.model_dump())


@router.put("/{profile_id}", response_model=ProfileResponse, dependencies=ADMIN)
async def update_profile(
    profile_id: uuid.UUID,
    data: ProfileUpdate,
    repo: SQLAlchemyRepository[Profile] = Depends(get_repo),
):
    profile = await repo.get_by_id(profile_id)
    if profile is None:
        raise HTTPException(status_code=404, detail="Profile not found")
    if profile.is_builtin:
        raise HTTPException(status_code=403, detail="Cannot modify built-in profiles")
    updated = await repo.update(profile_id, **data.model_dump(exclude_unset=True))
    return updated


@router.delete("/{profile_id}", status_code=204, dependencies=ADMIN)
async def delete_profile(
    profile_id: uuid.UUID, repo: SQLAlchemyRepository[Profile] = Depends(get_repo)
):
    profile = await repo.get_by_id(profile_id)
    if profile is None:
        raise HTTPException(status_code=404, detail="Profile not found")
    if profile.is_builtin:
        raise HTTPException(status_code=403, detail="Cannot delete built-in profiles")
    await repo.delete(profile_id)
