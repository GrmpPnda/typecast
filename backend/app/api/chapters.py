from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.engine import get_db
from app.models.chapter import Chapter
from app.repositories.sqlalchemy_repo import SQLAlchemyRepository
from app.schemas.chapter import (
    ChapterCreate,
    ChapterReorder,
    ChapterResponse,
    ChapterUpdate,
)

router = APIRouter()

FRONT_MATTER_TITLES = {
    "half title", "title page", "copyright", "dedication", "epigraph",
    "table of contents", "foreword", "preface", "acknowledgments",
    "acknowledgements", "introduction", "prologue",
}
BACK_MATTER_TITLES = {
    "epilogue", "afterword", "appendix", "glossary", "bibliography",
    "about the author", "also by", "colophon", "index",
}


def _classify_title(title: str | None) -> str:
    t = (title or "").lower().strip()
    if t in FRONT_MATTER_TITLES:
        return "front"
    if t in BACK_MATTER_TITLES:
        return "back"
    return "body"


def get_repo(db: AsyncSession = Depends(get_db)) -> SQLAlchemyRepository[Chapter]:
    return SQLAlchemyRepository(db, Chapter)


@router.get("/{work_id}/chapters", response_model=list[ChapterResponse])
async def list_chapters(
    work_id: uuid.UUID, repo: SQLAlchemyRepository[Chapter] = Depends(get_repo)
):
    return await repo.get_all(work_id=work_id)


@router.get("/chapters/{chapter_id}", response_model=ChapterResponse)
async def get_chapter(
    chapter_id: uuid.UUID, repo: SQLAlchemyRepository[Chapter] = Depends(get_repo)
):
    chapter = await repo.get_by_id(chapter_id)
    if chapter is None:
        raise HTTPException(status_code=404, detail="Chapter not found")
    return chapter


@router.post("/{work_id}/chapters", response_model=ChapterResponse, status_code=201)
async def create_chapter(
    work_id: uuid.UUID,
    data: ChapterCreate,
    db: AsyncSession = Depends(get_db),
):
    from sqlalchemy import select

    result = await db.execute(
        select(Chapter).where(Chapter.work_id == work_id)
    )
    existing = sorted(result.scalars().all(), key=lambda c: c.sort_order)

    classification = _classify_title(data.title)

    if classification == "front":
        first_body = next(
            (c for c in existing if _classify_title(c.title) == "body"), None
        )
        if first_body is not None:
            insert_at = first_body.sort_order
        else:
            insert_at = (existing[-1].sort_order + 1) if existing else 0
    elif classification == "back":
        insert_at = (existing[-1].sort_order + 1) if existing else 0
    else:
        last_body = None
        for c in existing:
            if _classify_title(c.title) in ("body", "front"):
                last_body = c
        first_back = next(
            (c for c in existing if _classify_title(c.title) == "back"), None
        )
        if first_back is not None:
            insert_at = first_back.sort_order
        elif last_body is not None:
            insert_at = last_body.sort_order + 1
        else:
            insert_at = (existing[-1].sort_order + 1) if existing else 0

    for ch in existing:
        if ch.sort_order >= insert_at:
            ch.sort_order += 1

    chapter = Chapter(
        work_id=work_id,
        sort_order=insert_at,
        **data.model_dump(exclude={"sort_order"}),
    )
    db.add(chapter)
    await db.commit()
    await db.refresh(chapter)
    return chapter


@router.put("/chapters/{chapter_id}", response_model=ChapterResponse)
async def update_chapter(
    chapter_id: uuid.UUID,
    data: ChapterUpdate,
    repo: SQLAlchemyRepository[Chapter] = Depends(get_repo),
):
    chapter = await repo.update(chapter_id, **data.model_dump(exclude_unset=True))
    if chapter is None:
        raise HTTPException(status_code=404, detail="Chapter not found")
    return chapter


@router.delete("/chapters/{chapter_id}", status_code=204)
async def delete_chapter(
    chapter_id: uuid.UUID, repo: SQLAlchemyRepository[Chapter] = Depends(get_repo)
):
    deleted = await repo.delete(chapter_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Chapter not found")


@router.put("/{work_id}/chapters/reorder", response_model=list[ChapterResponse])
async def reorder_chapters(
    work_id: uuid.UUID,
    data: ChapterReorder,
    db: AsyncSession = Depends(get_db),
):
    repo = SQLAlchemyRepository(db, Chapter)
    chapters = await repo.get_all(work_id=work_id)
    by_id = {ch.id: ch for ch in chapters}
    for item in data.chapters:
        ch = by_id.get(item.id)
        if ch is None:
            continue
        ch.sort_order = item.sort_order
        if item.number is not None:
            ch.number = item.number
    await db.commit()
    result = await repo.get_all(work_id=work_id)
    result.sort(key=lambda c: c.sort_order)
    return result
