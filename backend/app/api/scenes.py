from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.engine import get_db
from app.models.chapter import Chapter
from app.models.scene import Scene
from app.repositories.sqlalchemy_repo import SQLAlchemyRepository
from app.schemas.scene import SceneCreate, SceneResponse, SceneUpdate

router = APIRouter()


def get_scene_repo(db: AsyncSession = Depends(get_db)) -> SQLAlchemyRepository[Scene]:
    return SQLAlchemyRepository(db, Scene)


def get_chapter_repo(db: AsyncSession = Depends(get_db)) -> SQLAlchemyRepository[Chapter]:
    return SQLAlchemyRepository(db, Chapter)


@router.get("/chapters/{chapter_id}/scenes", response_model=list[SceneResponse])
async def list_scenes(
    chapter_id: uuid.UUID, db: AsyncSession = Depends(get_db)
):
    from sqlalchemy import select
    result = await db.execute(
        select(Scene)
        .where(Scene.chapter_id == chapter_id)
        .order_by(Scene.sort_order)
    )
    return list(result.scalars().all())


@router.get("/scenes/{scene_id}", response_model=SceneResponse)
async def get_scene(
    scene_id: uuid.UUID, repo: SQLAlchemyRepository[Scene] = Depends(get_scene_repo)
):
    scene = await repo.get_by_id(scene_id)
    if scene is None:
        raise HTTPException(status_code=404, detail="Scene not found")
    return scene


@router.post("/chapters/{chapter_id}/scenes", response_model=SceneResponse, status_code=201)
async def create_scene(
    chapter_id: uuid.UUID,
    data: SceneCreate,
    db: AsyncSession = Depends(get_db),
):
    from sqlalchemy import select, update

    result = await db.execute(select(Chapter).where(Chapter.id == chapter_id))
    chapter = result.scalar_one_or_none()
    if chapter is None:
        raise HTTPException(status_code=404, detail="Chapter not found")

    await db.execute(
        update(Scene)
        .where(Scene.chapter_id == chapter_id)
        .where(Scene.sort_order >= data.sort_order)
        .values(sort_order=Scene.sort_order + 1)
    )

    word_count = len(data.content.split()) if data.content else 0

    scene = Scene(
        chapter_id=chapter_id,
        title=data.title,
        content=data.content or "",
        sort_order=data.sort_order,
        word_count=word_count,
        status=data.status,
        pov_character=data.pov_character,
    )
    db.add(scene)
    await db.commit()
    await db.refresh(scene)
    return scene


@router.put("/scenes/{scene_id}", response_model=SceneResponse)
async def update_scene(
    scene_id: uuid.UUID,
    data: SceneUpdate,
    repo: SQLAlchemyRepository[Scene] = Depends(get_scene_repo),
):
    scene = await repo.get_by_id(scene_id)
    if scene is None:
        raise HTTPException(status_code=404, detail="Scene not found")

    update_fields = data.model_dump(exclude_unset=True)

    if "content" in update_fields and update_fields["content"] is not None:
        update_fields["word_count"] = len(update_fields["content"].split())

    if update_fields:
        scene = await repo.update(scene_id, **update_fields)

    return scene


@router.post("/scenes/{scene_id}/split", response_model=list[SceneResponse])
async def split_scene(
    scene_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
):
    """Split a scene at the first horizontal rule (---). Returns both scenes."""
    from sqlalchemy import select, update

    result = await db.execute(select(Scene).where(Scene.id == scene_id))
    scene = result.scalar_one_or_none()
    if scene is None:
        raise HTTPException(status_code=404, detail="Scene not found")

    content = scene.content or ""
    import re
    parts = re.split(r'\n---\n|\n\*\*\*\n|\n___\n', content, maxsplit=1)
    if len(parts) < 2:
        for sep in ['\n---', '---\n', '---']:
            if sep in content:
                idx = content.index(sep)
                parts = [content[:idx], content[idx + len(sep):]]
                break
    if len(parts) < 2:
        raise HTTPException(status_code=400, detail="No scene break found")

    before = parts[0].strip()
    after = parts[1].strip()

    await db.execute(
        update(Scene)
        .where(Scene.chapter_id == scene.chapter_id)
        .where(Scene.sort_order > scene.sort_order)
        .values(sort_order=Scene.sort_order + 1)
    )

    scene.content = before
    scene.word_count = len(before.split()) if before else 0

    new_scene = Scene(
        chapter_id=scene.chapter_id,
        content=after,
        sort_order=scene.sort_order + 1,
        word_count=len(after.split()) if after else 0,
        status=scene.status,
    )
    db.add(new_scene)
    await db.commit()
    await db.refresh(scene)
    await db.refresh(new_scene)
    return [scene, new_scene]


@router.delete("/scenes/{scene_id}", status_code=204)
async def delete_scene(
    scene_id: uuid.UUID, repo: SQLAlchemyRepository[Scene] = Depends(get_scene_repo)
):
    scene = await repo.get_by_id(scene_id)
    if scene is None:
        raise HTTPException(status_code=404, detail="Scene not found")
    await repo.delete(scene_id)
