from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.engine import get_db
from app.models.comment import Comment
from app.models.scene import Scene
from app.repositories.sqlalchemy_repo import SQLAlchemyRepository
from app.schemas.comment import CommentCreate, CommentResponse, CommentUpdate

router = APIRouter()


def get_comment_repo(
    db: AsyncSession = Depends(get_db),
) -> SQLAlchemyRepository[Comment]:
    return SQLAlchemyRepository(db, Comment)


@router.get("/scenes/{scene_id}/comments", response_model=list[CommentResponse])
async def list_comments(scene_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(Comment)
        .where(Comment.scene_id == scene_id)
        .order_by(Comment.anchor_from)
    )
    return list(result.scalars().all())


@router.get("/chapters/{chapter_id}/comments", response_model=list[CommentResponse])
async def list_chapter_comments(
    chapter_id: uuid.UUID, db: AsyncSession = Depends(get_db)
):
    result = await db.execute(
        select(Comment)
        .join(Scene, Comment.scene_id == Scene.id)
        .where(Scene.chapter_id == chapter_id)
        .order_by(Scene.sort_order, Comment.anchor_from)
    )
    return list(result.scalars().all())


@router.post(
    "/scenes/{scene_id}/comments",
    response_model=CommentResponse,
    status_code=201,
)
async def create_comment(
    scene_id: uuid.UUID,
    data: CommentCreate,
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Scene).where(Scene.id == scene_id))
    if result.scalar_one_or_none() is None:
        raise HTTPException(status_code=404, detail="Scene not found")

    comment = Comment(
        scene_id=scene_id,
        anchor_text=data.anchor_text,
        anchor_from=data.anchor_from,
        anchor_to=data.anchor_to,
        content=data.content,
        suggestion=data.suggestion,
        author=data.author,
    )
    db.add(comment)
    await db.commit()
    await db.refresh(comment)
    return comment


@router.post(
    "/scenes/{scene_id}/comments/batch",
    response_model=list[CommentResponse],
    status_code=201,
)
async def batch_create_comments(
    scene_id: uuid.UUID,
    data: list[CommentCreate],
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Scene).where(Scene.id == scene_id))
    if result.scalar_one_or_none() is None:
        raise HTTPException(status_code=404, detail="Scene not found")

    comments = []
    for item in data:
        comment = Comment(
            scene_id=scene_id,
            anchor_text=item.anchor_text,
            anchor_from=item.anchor_from,
            anchor_to=item.anchor_to,
            content=item.content,
            suggestion=item.suggestion,
            author=item.author,
        )
        db.add(comment)
        comments.append(comment)
    await db.commit()
    for c in comments:
        await db.refresh(c)
    return comments


@router.put("/comments/{comment_id}", response_model=CommentResponse)
async def update_comment(
    comment_id: uuid.UUID,
    data: CommentUpdate,
    repo: SQLAlchemyRepository[Comment] = Depends(get_comment_repo),
):
    comment = await repo.get_by_id(comment_id)
    if comment is None:
        raise HTTPException(status_code=404, detail="Comment not found")

    update_fields = data.model_dump(exclude_unset=True)
    if update_fields:
        comment = await repo.update(comment_id, **update_fields)
    return comment


@router.delete("/comments/{comment_id}", status_code=204)
async def delete_comment(
    comment_id: uuid.UUID,
    repo: SQLAlchemyRepository[Comment] = Depends(get_comment_repo),
):
    comment = await repo.get_by_id(comment_id)
    if comment is None:
        raise HTTPException(status_code=404, detail="Comment not found")
    await repo.delete(comment_id)


@router.post("/scenes/{scene_id}/comments/resolve-all", status_code=200)
async def resolve_all_comments(
    scene_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
):
    from sqlalchemy import update

    await db.execute(
        update(Comment)
        .where(Comment.scene_id == scene_id)
        .where(Comment.resolved.is_(False))
        .values(resolved=True)
    )
    await db.commit()
    return {"resolved": True}


@router.post("/comments/{comment_id}/apply", status_code=200)
async def apply_comment_suggestion(
    comment_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Comment).where(Comment.id == comment_id))
    comment = result.scalar_one_or_none()
    if comment is None:
        raise HTTPException(status_code=404, detail="Comment not found")
    if not comment.suggestion:
        raise HTTPException(status_code=400, detail="Comment has no suggestion")

    result = await db.execute(select(Scene).where(Scene.id == comment.scene_id))
    scene = result.scalar_one_or_none()
    if scene is None:
        raise HTTPException(status_code=404, detail="Scene not found")

    if scene.checkpoint is None:
        scene.checkpoint = scene.content

    content = scene.content or ""
    anchor = comment.anchor_text

    from app.services.ai_tools import _find_anchor
    idx, anchor_len = _find_anchor(content, anchor, comment.anchor_from, comment.anchor_to)

    if idx == -1:
        raise HTTPException(
            status_code=409,
            detail="Anchor text no longer found in scene content",
        )

    scene.content = content[:idx] + comment.suggestion + content[idx + anchor_len:]
    scene.word_count = len(scene.content.split()) if scene.content else 0
    comment.resolved = True
    await db.commit()
    await db.refresh(scene)
    return {"scene_id": str(scene.id), "content": scene.content, "checkpoint": scene.checkpoint}


@router.post("/scenes/{scene_id}/revert", status_code=200)
async def revert_scene(
    scene_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Scene).where(Scene.id == scene_id))
    scene = result.scalar_one_or_none()
    if scene is None:
        raise HTTPException(status_code=404, detail="Scene not found")
    if scene.checkpoint is None:
        raise HTTPException(status_code=400, detail="No checkpoint to revert to")

    scene.content = scene.checkpoint
    scene.checkpoint = None
    scene.word_count = len(scene.content.split()) if scene.content else 0

    from sqlalchemy import update as sql_update
    await db.execute(
        sql_update(Comment)
        .where(Comment.scene_id == scene_id)
        .where(Comment.suggestion.isnot(None))
        .where(Comment.resolved.is_(True))
        .values(resolved=False)
    )

    await db.commit()
    await db.refresh(scene)
    return {"scene_id": str(scene.id), "content": scene.content}


@router.post("/scenes/{scene_id}/checkpoint/clear", status_code=200)
async def clear_checkpoint(
    scene_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Scene).where(Scene.id == scene_id))
    scene = result.scalar_one_or_none()
    if scene is None:
        raise HTTPException(status_code=404, detail="Scene not found")

    scene.checkpoint = None
    await db.commit()
    return {"scene_id": str(scene.id)}


@router.post("/scenes/{scene_id}/rewrite", status_code=200)
async def rewrite_scene_from_comments(
    scene_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Scene).where(Scene.id == scene_id))
    scene = result.scalar_one_or_none()
    if scene is None:
        raise HTTPException(status_code=404, detail="Scene not found")

    result = await db.execute(
        select(Comment)
        .where(Comment.scene_id == scene_id)
        .where(Comment.resolved.is_(False))
        .order_by(Comment.anchor_from)
    )
    comments = list(result.scalars().all())
    if not comments:
        raise HTTPException(status_code=400, detail="No unresolved comments to apply")

    from app.services.ai import get_ai_provider

    provider = await get_ai_provider(db)

    sibling_context = ""
    chapter_result = await db.execute(
        select(Scene)
        .where(Scene.chapter_id == scene.chapter_id)
        .where(Scene.id != scene_id)
        .order_by(Scene.sort_order)
    )
    siblings = list(chapter_result.scalars().all())
    if siblings:
        style_lines = []
        for sib in siblings:
            if sib.content and sib.content.strip():
                style_lines.append(sib.content[:2000])
        if style_lines:
            sibling_context = (
                "\n\n## Other Scenes in This Chapter (for style reference)\n"
                "Study this prose carefully — your rewrite must be "
                "indistinguishable in style from the author's writing.\n\n"
                + "\n\n---\n\n".join(style_lines)
            )

    feedback_lines = []
    for c in comments:
        line = f'- On "{c.anchor_text}": {c.content}'
        if c.suggestion:
            line += f' [Suggested replacement: "{c.suggestion}"]'
        feedback_lines.append(line)
    feedback = "\n".join(feedback_lines)

    prompt = (
        "Rewrite the following scene incorporating ALL of the reviewer feedback below. "
        "Your rewrite MUST match the author's prose style exactly — study the other "
        "scenes provided for reference. Match their sentence structure, vocabulary "
        "level, dialogue style, description density, and narrative distance. "
        "Make only the changes indicated by the feedback — do not add, remove, or "
        "restructure content beyond what the feedback requires. Return ONLY the "
        "rewritten scene content as markdown with no preamble, explanation, "
        "or wrapping.\n\n"
        f"## Reviewer Feedback\n{feedback}\n\n"
        f"## Scene to Rewrite\n{scene.content}"
        f"{sibling_context}"
    )

    try:
        rewritten = await provider.generate(prompt)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"AI generation failed: {exc}")

    rewritten = rewritten.strip()
    if not rewritten:
        raise HTTPException(status_code=502, detail="AI returned empty content")

    if scene.checkpoint is None:
        scene.checkpoint = scene.content

    scene.content = rewritten
    scene.word_count = len(rewritten.split())

    from sqlalchemy import update as sql_update
    await db.execute(
        sql_update(Comment)
        .where(Comment.scene_id == scene_id)
        .where(Comment.resolved.is_(False))
        .values(resolved=True)
    )

    await db.commit()
    await db.refresh(scene)
    return {"scene_id": str(scene.id), "content": scene.content, "checkpoint": scene.checkpoint}
