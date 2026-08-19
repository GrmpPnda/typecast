"""Global image gallery: aggregates work-gallery images, covers, and codex images."""

from __future__ import annotations

import logging
import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app import paths
from app.api.deps import get_current_user
from app.db.engine import get_db
from app.models.codex import CodexEntry
from app.models.codex_association import CodexAssociation
from app.models.codex_image import CodexImage
from app.models.image import Image
from app.models.series import Series
from app.models.user import User
from app.models.work import Work
from app.schemas.gallery import (
    BulkDeleteRequest,
    GalleryImageUpdate,
    GalleryItem,
    ReassignRequest,
)

logger = logging.getLogger(__name__)
router = APIRouter()

UPLOAD_DIR = paths.UPLOAD_DIR


async def _user_work_map(db: AsyncSession, user: User) -> dict[uuid.UUID, Work]:
    """Return a map of work_id -> Work for all works owned by the user."""
    result = await db.execute(select(Work).where(Work.user_id == user.id))
    works = result.scalars().all()
    return {w.id: w for w in works}


@router.get("", response_model=list[GalleryItem])
async def list_gallery(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """List every image across the user's works: galleries, covers, and codex entries."""
    work_map = await _user_work_map(db, user)
    work_ids = list(work_map.keys())
    logger.debug("Building gallery for user %s across %d works", user.email, len(work_ids))

    items: list[GalleryItem] = []
    if not work_ids:
        return items

    # 1. Work gallery images
    img_result = await db.execute(select(Image).where(Image.work_id.in_(work_ids)))
    for img in img_result.scalars().all():
        work = work_map.get(img.work_id)
        items.append(
            GalleryItem(
                id=f"image:{img.id}",
                source="gallery",
                url=img.url,
                original_name=img.original_name,
                mime_type=img.mime_type,
                size_bytes=img.size_bytes,
                width=img.width,
                height=img.height,
                alt_text=img.alt_text or "",
                tags=img.tags or "",
                work_id=img.work_id,
                work_title=work.title if work else None,
                manageable=True,
                created_at=img.created_at,
            )
        )

    # 2. Work covers
    for work in work_map.values():
        if work.cover_image_path:
            items.append(
                GalleryItem(
                    id=f"cover:{work.id}",
                    source="cover",
                    url=work.cover_image_path,
                    original_name=f"{work.title} — cover",
                    alt_text=f"Cover of {work.title}",
                    work_id=work.id,
                    work_title=work.title,
                    manageable=False,
                    created_at=work.created_at,
                )
            )

    # 3. Codex entry images — entries link to works/series via associations.
    # Include entries associated with any of the user's works or series.
    series_result = await db.execute(select(Series.id).where(Series.user_id == user.id))
    series_ids = [row[0] for row in series_result.all()]
    target_ids = work_ids + series_ids
    if target_ids:
        codex_result = await db.execute(
            select(CodexImage, CodexEntry, CodexAssociation.target_id, CodexAssociation.target_type)
            .join(CodexEntry, CodexImage.codex_entry_id == CodexEntry.id)
            .join(CodexAssociation, CodexAssociation.codex_entry_id == CodexEntry.id)
            .where(CodexAssociation.target_id.in_(target_ids))
        )
        seen_codex: set[uuid.UUID] = set()
        for ci, entry, target_id, target_type in codex_result.all():
            if ci.id in seen_codex:
                continue
            seen_codex.add(ci.id)
            resolved_work_id = target_id if target_type == "work" else None
            items.append(
                GalleryItem(
                    id=f"codex:{ci.id}",
                    source="codex",
                    url=ci.url,
                    original_name=ci.original_name,
                    mime_type=ci.mime_type,
                    size_bytes=ci.size_bytes,
                    width=ci.width,
                    height=ci.height,
                    alt_text=ci.alt_text or "",
                    work_id=resolved_work_id,
                    work_title=work_map[resolved_work_id].title
                    if resolved_work_id in work_map else None,
                    codex_entry_id=entry.id,
                    codex_entry_name=entry.name,
                    manageable=False,
                    created_at=ci.created_at,
                )
            )

    logger.info("Gallery for %s returned %d items", user.email, len(items))
    return items


async def _get_owned_image(db: AsyncSession, image_id: uuid.UUID, user: User) -> Image:
    """Fetch a gallery image, verifying it belongs to one of the user's works."""
    result = await db.execute(select(Image).where(Image.id == image_id))
    image = result.scalar_one_or_none()
    if image is None:
        raise HTTPException(status_code=404, detail="Image not found")
    work = await db.get(Work, image.work_id)
    if work is None or work.user_id != user.id:
        logger.warning("User %s attempted to access image %s they do not own", user.email, image_id)
        raise HTTPException(status_code=403, detail="Not authorized for this image")
    return image


@router.put("/images/{image_id}", response_model=GalleryItem)
async def update_gallery_image(
    image_id: uuid.UUID,
    data: GalleryImageUpdate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Update alt text and/or tags on a gallery image."""
    image = await _get_owned_image(db, image_id, user)
    if data.alt_text is not None:
        image.alt_text = data.alt_text
    if data.tags is not None:
        image.tags = data.tags
    await db.commit()
    await db.refresh(image)
    work = await db.get(Work, image.work_id)
    logger.info("Updated gallery image %s (alt/tags)", image_id)
    return GalleryItem(
        id=f"image:{image.id}",
        source="gallery",
        url=image.url,
        original_name=image.original_name,
        mime_type=image.mime_type,
        size_bytes=image.size_bytes,
        width=image.width,
        height=image.height,
        alt_text=image.alt_text or "",
        tags=image.tags or "",
        work_id=image.work_id,
        work_title=work.title if work else None,
        manageable=True,
        created_at=image.created_at,
    )


@router.put("/images/{image_id}/reassign", response_model=GalleryItem)
async def reassign_image(
    image_id: uuid.UUID,
    data: ReassignRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Move a gallery image to a different work, relocating its file on disk."""
    image = await _get_owned_image(db, image_id, user)
    target = await db.get(Work, data.work_id)
    if target is None or target.user_id != user.id:
        raise HTTPException(status_code=404, detail="Target work not found")
    if target.id == image.work_id:
        raise HTTPException(status_code=400, detail="Image already belongs to that work")

    old_path = UPLOAD_DIR / "images" / str(image.work_id) / image.filename
    new_dir = UPLOAD_DIR / "images" / str(target.id)
    new_dir.mkdir(parents=True, exist_ok=True)
    new_path = new_dir / image.filename
    if old_path.exists():
        old_path.rename(new_path)
    else:
        logger.warning("Reassign: source file missing for image %s at %s", image_id, old_path)

    old_work_id = image.work_id
    image.work_id = target.id
    await db.commit()
    await db.refresh(image)
    logger.info("Reassigned image %s from work %s to %s", image_id, old_work_id, target.id)
    return GalleryItem(
        id=f"image:{image.id}",
        source="gallery",
        url=image.url,
        original_name=image.original_name,
        mime_type=image.mime_type,
        size_bytes=image.size_bytes,
        width=image.width,
        height=image.height,
        alt_text=image.alt_text or "",
        tags=image.tags or "",
        work_id=image.work_id,
        work_title=target.title,
        manageable=True,
        created_at=image.created_at,
    )


@router.post("/images/bulk-delete", status_code=204)
async def bulk_delete_images(
    data: BulkDeleteRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Delete multiple gallery images (and their files) owned by the user."""
    deleted = 0
    for image_id in data.image_ids:
        result = await db.execute(select(Image).where(Image.id == image_id))
        image = result.scalar_one_or_none()
        if image is None:
            continue
        work = await db.get(Work, image.work_id)
        if work is None or work.user_id != user.id:
            logger.warning("Bulk delete skipped image %s not owned by %s", image_id, user.email)
            continue
        file_path = UPLOAD_DIR / "images" / str(image.work_id) / image.filename
        if file_path.exists():
            file_path.unlink()
        await db.delete(image)
        deleted += 1
    await db.commit()
    logger.info("Bulk-deleted %d/%d images for %s", deleted, len(data.image_ids), user.email)
