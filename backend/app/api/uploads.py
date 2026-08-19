from __future__ import annotations

import uuid
from pathlib import Path

import aiofiles
from fastapi import APIRouter, Depends, HTTPException, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from app import paths
from app.db.engine import get_db
from app.models.series import Series
from app.models.work import Work
from app.repositories.sqlalchemy_repo import SQLAlchemyRepository

router = APIRouter()

UPLOAD_DIR = paths.UPLOAD_DIR
ALLOWED_TYPES = {"image/jpeg", "image/png", "image/webp", "image/gif"}
MAX_SIZE = 10 * 1024 * 1024


def get_repo(db: AsyncSession = Depends(get_db)) -> SQLAlchemyRepository[Work]:
    return SQLAlchemyRepository(db, Work)


@router.post("/works/{work_id}/cover")
async def upload_cover(
    work_id: uuid.UUID,
    file: UploadFile,
    repo: SQLAlchemyRepository[Work] = Depends(get_repo),
):
    work = await repo.get_by_id(work_id)
    if work is None:
        raise HTTPException(status_code=404, detail="Work not found")

    if file.content_type not in ALLOWED_TYPES:
        raise HTTPException(status_code=400, detail="File must be JPEG, PNG, WebP, or GIF")

    data = await file.read()
    if len(data) > MAX_SIZE:
        raise HTTPException(status_code=400, detail="File must be under 10 MB")

    ext = Path(file.filename or "image.jpg").suffix.lower() or ".jpg"
    filename = f"{work_id}{ext}"
    dest = UPLOAD_DIR / "covers" / filename

    dest.parent.mkdir(parents=True, exist_ok=True)

    if work.cover_image_path:
        old = UPLOAD_DIR / work.cover_image_path.lstrip("/uploads/")
        if old.exists():
            old.unlink()

    async with aiofiles.open(dest, "wb") as f:
        await f.write(data)

    relative_path = f"/uploads/covers/{filename}"
    await repo.update(work_id, cover_image_path=relative_path)

    return {"cover_image_path": relative_path}


@router.delete("/works/{work_id}/cover", status_code=204)
async def delete_cover(
    work_id: uuid.UUID,
    repo: SQLAlchemyRepository[Work] = Depends(get_repo),
):
    work = await repo.get_by_id(work_id)
    if work is None:
        raise HTTPException(status_code=404, detail="Work not found")

    if work.cover_image_path:
        old = UPLOAD_DIR / work.cover_image_path.lstrip("/uploads/")
        if old.exists():
            old.unlink()

    await repo.update(work_id, cover_image_path=None)


@router.post("/works/{work_id}/cover-from-image")
async def set_cover_from_image(
    work_id: uuid.UUID,
    body: dict,
    repo: SQLAlchemyRepository[Work] = Depends(get_repo),
):
    """Set a work's cover from an existing image URL (from the gallery)."""
    import shutil

    work = await repo.get_by_id(work_id)
    if work is None:
        raise HTTPException(status_code=404, detail="Work not found")

    image_url: str = body.get("image_url", "")
    if not image_url.startswith("/uploads/"):
        raise HTTPException(status_code=400, detail="Invalid image path")

    src = UPLOAD_DIR / image_url.removeprefix("/uploads/")
    if not src.exists():
        raise HTTPException(status_code=404, detail="Source image not found")

    ext = src.suffix.lower() or ".jpg"
    filename = f"{work_id}{ext}"
    dest = UPLOAD_DIR / "covers" / filename
    dest.parent.mkdir(parents=True, exist_ok=True)

    if work.cover_image_path:
        old = UPLOAD_DIR / work.cover_image_path.removeprefix("/uploads/")
        if old.exists() and old != src:
            old.unlink()

    shutil.copy2(str(src), str(dest))

    relative_path = f"/uploads/covers/{filename}"
    await repo.update(work_id, cover_image_path=relative_path)
    return {"cover_image_path": relative_path}


def get_series_repo(db: AsyncSession = Depends(get_db)) -> SQLAlchemyRepository[Series]:
    return SQLAlchemyRepository(db, Series)


@router.post("/series/{series_id}/cover")
async def upload_series_cover(
    series_id: uuid.UUID,
    file: UploadFile,
    repo: SQLAlchemyRepository[Series] = Depends(get_series_repo),
):
    s = await repo.get_by_id(series_id)
    if s is None:
        raise HTTPException(status_code=404, detail="Series not found")

    if file.content_type not in ALLOWED_TYPES:
        raise HTTPException(status_code=400, detail="File must be JPEG, PNG, WebP, or GIF")

    data = await file.read()
    if len(data) > MAX_SIZE:
        raise HTTPException(status_code=400, detail="File must be under 10 MB")

    ext = Path(file.filename or "image.jpg").suffix.lower() or ".jpg"
    filename = f"series_{series_id}{ext}"
    dest = UPLOAD_DIR / "covers" / filename

    dest.parent.mkdir(parents=True, exist_ok=True)

    if s.cover_image_path:
        old = UPLOAD_DIR / s.cover_image_path.lstrip("/uploads/")
        if old.exists():
            old.unlink()

    async with aiofiles.open(dest, "wb") as f:
        await f.write(data)

    relative_path = f"/uploads/covers/{filename}"
    await repo.update(series_id, cover_image_path=relative_path)

    return {"cover_image_path": relative_path}


@router.post("/series/{series_id}/cover-from-image")
async def set_series_cover_from_image(
    series_id: uuid.UUID,
    body: dict,
    repo: SQLAlchemyRepository[Series] = Depends(get_series_repo),
):
    """Set a series banner from an existing image URL."""
    import shutil

    s = await repo.get_by_id(series_id)
    if s is None:
        raise HTTPException(status_code=404, detail="Series not found")

    image_url: str = body.get("image_url", "")
    if not image_url.startswith("/uploads/"):
        raise HTTPException(status_code=400, detail="Invalid image path")

    src = UPLOAD_DIR / image_url.removeprefix("/uploads/")
    if not src.exists():
        raise HTTPException(status_code=404, detail="Source image not found")

    ext = src.suffix.lower() or ".jpg"
    filename = f"series_{series_id}{ext}"
    dest = UPLOAD_DIR / "covers" / filename
    dest.parent.mkdir(parents=True, exist_ok=True)

    if s.cover_image_path:
        old = UPLOAD_DIR / s.cover_image_path.removeprefix("/uploads/")
        if old.exists() and old != src:
            old.unlink()

    shutil.copy2(str(src), str(dest))

    relative_path = f"/uploads/covers/{filename}"
    await repo.update(series_id, cover_image_path=relative_path)
    return {"cover_image_path": relative_path}


@router.delete("/series/{series_id}/cover", status_code=204)
async def delete_series_cover(
    series_id: uuid.UUID,
    repo: SQLAlchemyRepository[Series] = Depends(get_series_repo),
):
    s = await repo.get_by_id(series_id)
    if s is None:
        raise HTTPException(status_code=404, detail="Series not found")

    if s.cover_image_path:
        old = UPLOAD_DIR / s.cover_image_path.lstrip("/uploads/")
        if old.exists():
            old.unlink()

    await repo.update(series_id, cover_image_path=None)
