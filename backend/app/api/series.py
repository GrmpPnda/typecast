from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.db.engine import get_db
from app.models.series import Series
from app.models.user import User
from app.repositories.sqlalchemy_repo import SQLAlchemyRepository
from app.schemas.series import SeriesCreate, SeriesResponse, SeriesUpdate

router = APIRouter()


def get_repo(db: AsyncSession = Depends(get_db)) -> SQLAlchemyRepository[Series]:
    return SQLAlchemyRepository(db, Series)


@router.get("/", response_model=list[SeriesResponse])
async def list_series(
    user: User = Depends(get_current_user),
    repo: SQLAlchemyRepository[Series] = Depends(get_repo),
):
    return await repo.get_all(user_id=user.id)


@router.get("/{series_id}", response_model=SeriesResponse)
async def get_series(
    series_id: uuid.UUID, repo: SQLAlchemyRepository[Series] = Depends(get_repo)
):
    series = await repo.get_by_id(series_id)
    if series is None:
        raise HTTPException(status_code=404, detail="Series not found")
    return series


@router.post("/", response_model=SeriesResponse, status_code=201)
async def create_series(
    data: SeriesCreate,
    user: User = Depends(get_current_user),
    repo: SQLAlchemyRepository[Series] = Depends(get_repo),
):
    return await repo.create(user_id=user.id, **data.model_dump())


@router.patch("/{series_id}", response_model=SeriesResponse)
async def update_series(
    series_id: uuid.UUID,
    data: SeriesUpdate,
    repo: SQLAlchemyRepository[Series] = Depends(get_repo),
):
    series = await repo.update(series_id, **data.model_dump(exclude_unset=True))
    if series is None:
        raise HTTPException(status_code=404, detail="Series not found")
    return series


@router.delete("/{series_id}", status_code=204)
async def delete_series(
    series_id: uuid.UUID, repo: SQLAlchemyRepository[Series] = Depends(get_repo)
):
    deleted = await repo.delete(series_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Series not found")
