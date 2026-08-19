from __future__ import annotations

import struct
import uuid
from pathlib import Path

import aiofiles
from fastapi import APIRouter, Depends, HTTPException, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from app import paths
from app.db.engine import get_db
from app.models.image import Image
from app.models.work import Work
from app.repositories.sqlalchemy_repo import SQLAlchemyRepository
from app.schemas.image import ImageResponse, ImageUpdate

router = APIRouter()

UPLOAD_DIR = paths.UPLOAD_DIR
ALLOWED_TYPES = {"image/jpeg", "image/png", "image/webp", "image/gif"}
MAX_SIZE = 10 * 1024 * 1024


def get_work_repo(db: AsyncSession = Depends(get_db)) -> SQLAlchemyRepository[Work]:
    return SQLAlchemyRepository(db, Work)


def get_image_repo(db: AsyncSession = Depends(get_db)) -> SQLAlchemyRepository[Image]:
    return SQLAlchemyRepository(db, Image)


def _image_dimensions(data: bytes, mime: str) -> tuple[int | None, int | None]:
    try:
        if mime == "image/png" and data[:8] == b"\x89PNG\r\n\x1a\n":
            w, h = struct.unpack(">II", data[16:24])
            return int(w), int(h)
        if mime == "image/jpeg":
            i = 2
            while i < len(data) - 1:
                if data[i] != 0xFF:
                    break
                marker = data[i + 1]
                if marker in (0xC0, 0xC1, 0xC2):
                    h, w = struct.unpack(">HH", data[i + 5:i + 9])
                    return int(w), int(h)
                length = struct.unpack(">H", data[i + 2:i + 4])[0]
                i += 2 + length
    except Exception:
        pass
    return None, None


@router.get("/images/all", response_model=list[ImageResponse])
async def list_all_images(
    image_repo: SQLAlchemyRepository[Image] = Depends(get_image_repo),
):
    """List all images across all works."""
    return await image_repo.get_all()


@router.get("/{work_id}/images", response_model=list[ImageResponse])
async def list_images(
    work_id: uuid.UUID,
    work_repo: SQLAlchemyRepository[Work] = Depends(get_work_repo),
    image_repo: SQLAlchemyRepository[Image] = Depends(get_image_repo),
):
    work = await work_repo.get_by_id(work_id)
    if work is None:
        raise HTTPException(status_code=404, detail="Work not found")
    return await image_repo.get_all(work_id=work_id)


@router.post("/{work_id}/images", response_model=ImageResponse, status_code=201)
async def upload_image(
    work_id: uuid.UUID,
    file: UploadFile,
    work_repo: SQLAlchemyRepository[Work] = Depends(get_work_repo),
    image_repo: SQLAlchemyRepository[Image] = Depends(get_image_repo),
):
    work = await work_repo.get_by_id(work_id)
    if work is None:
        raise HTTPException(status_code=404, detail="Work not found")

    if file.content_type not in ALLOWED_TYPES:
        raise HTTPException(status_code=400, detail="File must be JPEG, PNG, WebP, or GIF")

    data = await file.read()
    if len(data) > MAX_SIZE:
        raise HTTPException(status_code=400, detail="File must be under 10 MB")

    original_name = file.filename or "image.jpg"
    ext = Path(original_name).suffix.lower() or ".jpg"
    image_id = uuid.uuid4()
    filename = f"{image_id}{ext}"

    dest_dir = UPLOAD_DIR / "images" / str(work_id)
    dest_dir.mkdir(parents=True, exist_ok=True)

    async with aiofiles.open(dest_dir / filename, "wb") as f:
        await f.write(data)

    width, height = _image_dimensions(data, file.content_type or "")

    image = await image_repo.create(
        id=image_id,
        work_id=work_id,
        filename=filename,
        original_name=original_name,
        mime_type=file.content_type or "application/octet-stream",
        size_bytes=len(data),
        width=width,
        height=height,
    )
    return image


@router.put("/images/{image_id}", response_model=ImageResponse)
async def update_image(
    image_id: uuid.UUID,
    data: ImageUpdate,
    image_repo: SQLAlchemyRepository[Image] = Depends(get_image_repo),
):
    image = await image_repo.update(image_id, **data.model_dump(exclude_unset=True))
    if image is None:
        raise HTTPException(status_code=404, detail="Image not found")
    return image


@router.delete("/images/{image_id}", status_code=204)
async def delete_image(
    image_id: uuid.UUID,
    image_repo: SQLAlchemyRepository[Image] = Depends(get_image_repo),
):
    image = await image_repo.get_by_id(image_id)
    if image is None:
        raise HTTPException(status_code=404, detail="Image not found")

    file_path = UPLOAD_DIR / "images" / str(image.work_id) / image.filename
    if file_path.exists():
        file_path.unlink()

    await image_repo.delete(image_id)
