from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.api.ownership import require_owned
from app.db.engine import get_db
from app.models.user import User
from app.models.work import Work
from app.repositories.sqlalchemy_repo import SQLAlchemyRepository
from app.schemas.work import WorkCreate, WorkResponse, WorkUpdate

router = APIRouter()


def get_repo(db: AsyncSession = Depends(get_db)) -> SQLAlchemyRepository[Work]:
    return SQLAlchemyRepository(db, Work)


@router.get("/", response_model=list[WorkResponse])
async def list_works(
    series_id: uuid.UUID | None = Query(None),
    user: User = Depends(get_current_user),
    repo: SQLAlchemyRepository[Work] = Depends(get_repo),
):
    return await repo.get_all(series_id=series_id, user_id=user.id)


@router.get("/{work_id}", response_model=WorkResponse)
async def get_work(
    work_id: uuid.UUID, repo: SQLAlchemyRepository[Work] = Depends(get_repo)
):
    work = await repo.get_by_id(work_id)
    if work is None:
        raise HTTPException(status_code=404, detail="Work not found")
    return work


@router.post("/", response_model=WorkResponse, status_code=201)
async def create_work(
    data: WorkCreate,
    user: User = Depends(get_current_user),
    repo: SQLAlchemyRepository[Work] = Depends(get_repo),
    db: AsyncSession = Depends(get_db),
):
    await require_owned(db, user, "series", data.series_id)
    return await repo.create(user_id=user.id, **data.model_dump())


@router.put("/{work_id}", response_model=WorkResponse)
async def update_work(
    work_id: uuid.UUID,
    data: WorkUpdate,
    repo: SQLAlchemyRepository[Work] = Depends(get_repo),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    # Moving your work into someone else's series would add it to their library.
    await require_owned(db, user, "series", data.series_id)
    work = await repo.update(work_id, **data.model_dump(exclude_unset=True))
    if work is None:
        raise HTTPException(status_code=404, detail="Work not found")
    return work


@router.delete("/{work_id}", status_code=204)
async def delete_work(
    work_id: uuid.UUID, repo: SQLAlchemyRepository[Work] = Depends(get_repo)
):
    deleted = await repo.delete(work_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Work not found")
