from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.engine import get_db
from app.models.section import Section, SectionPlacement
from app.repositories.sqlalchemy_repo import SQLAlchemyRepository
from app.schemas.section import SectionCreate, SectionResponse, SectionUpdate

router = APIRouter()


def get_repo(db: AsyncSession = Depends(get_db)) -> SQLAlchemyRepository[Section]:
    return SQLAlchemyRepository(db, Section)


@router.get("/{work_id}/sections", response_model=list[SectionResponse])
async def list_sections(
    work_id: uuid.UUID,
    placement: SectionPlacement | None = Query(None),
    repo: SQLAlchemyRepository[Section] = Depends(get_repo),
):
    return await repo.get_all(work_id=work_id, placement=placement)


@router.get("/sections/{section_id}", response_model=SectionResponse)
async def get_section(
    section_id: uuid.UUID, repo: SQLAlchemyRepository[Section] = Depends(get_repo)
):
    section = await repo.get_by_id(section_id)
    if section is None:
        raise HTTPException(status_code=404, detail="Section not found")
    return section


@router.post("/{work_id}/sections", response_model=SectionResponse, status_code=201)
async def create_section(
    work_id: uuid.UUID,
    data: SectionCreate,
    repo: SQLAlchemyRepository[Section] = Depends(get_repo),
):
    return await repo.create(work_id=work_id, **data.model_dump())


@router.put("/sections/{section_id}", response_model=SectionResponse)
async def update_section(
    section_id: uuid.UUID,
    data: SectionUpdate,
    repo: SQLAlchemyRepository[Section] = Depends(get_repo),
):
    section = await repo.update(section_id, **data.model_dump(exclude_unset=True))
    if section is None:
        raise HTTPException(status_code=404, detail="Section not found")
    return section


@router.delete("/sections/{section_id}", status_code=204)
async def delete_section(
    section_id: uuid.UUID, repo: SQLAlchemyRepository[Section] = Depends(get_repo)
):
    deleted = await repo.delete(section_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Section not found")
