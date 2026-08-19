from __future__ import annotations

import struct
import uuid
from pathlib import Path

import aiofiles
from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app import paths
from app.db.engine import get_db
from app.models.codex import CodexEntry, EntryType
from app.models.codex_association import CodexAssociation
from app.models.codex_image import CodexImage
from app.schemas.codex import CodexCreate, CodexResponse, CodexUpdate
from app.schemas.codex_image import CodexImageResponse, CodexImageUpdate

router = APIRouter()

UPLOAD_DIR = paths.UPLOAD_DIR
ALLOWED_TYPES = {"image/jpeg", "image/png", "image/webp", "image/gif"}
MAX_SIZE = 10 * 1024 * 1024


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


def _entry_to_response(entry: CodexEntry) -> CodexResponse:
    work_ids = []
    series_ids = []
    for assoc in entry.associations or []:
        if assoc.target_type == "work":
            work_ids.append(assoc.target_id)
        elif assoc.target_type == "series":
            series_ids.append(assoc.target_id)
    images = sorted(entry.images or [], key=lambda img: (not img.is_primary, img.created_at))
    primary = next((img for img in images if img.is_primary), None)
    if not primary and images:
        primary = images[0]
    return CodexResponse(
        id=entry.id,
        entry_type=entry.entry_type,
        name=entry.name,
        description=entry.description,
        content=entry.content,
        tags=entry.tags,
        metadata=entry.metadata_,
        notes=entry.notes,
        voice_id=entry.voice_id,
        work_ids=work_ids,
        series_ids=series_ids,
        images=[CodexImageResponse.model_validate(img) for img in images],
        primary_image_url=primary.url if primary else None,
        created_at=entry.created_at,
        updated_at=entry.updated_at,
    )


@router.get("/", response_model=list[CodexResponse])
async def list_codex_entries(
    entry_type: EntryType | None = Query(None),
    tag: str | None = Query(None),
    work_id: uuid.UUID | None = Query(None),
    series_id: uuid.UUID | None = Query(None),
    db: AsyncSession = Depends(get_db),
):
    stmt = select(CodexEntry).options(
        selectinload(CodexEntry.associations),
        selectinload(CodexEntry.images),
    )
    if entry_type is not None:
        stmt = stmt.where(CodexEntry.entry_type == entry_type)
    if tag is not None:
        stmt = stmt.where(CodexEntry.tags.contains(tag))
    if work_id is not None:
        stmt = stmt.join(CodexAssociation).where(
            CodexAssociation.target_type == "work",
            CodexAssociation.target_id == work_id,
        )
    if series_id is not None:
        stmt = stmt.join(CodexAssociation).where(
            CodexAssociation.target_type == "series",
            CodexAssociation.target_id == series_id,
        )
    result = await db.execute(stmt)
    return [_entry_to_response(e) for e in result.scalars().unique().all()]


@router.get("/{entry_id}", response_model=CodexResponse)
async def get_codex_entry(
    entry_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(CodexEntry)
        .where(CodexEntry.id == entry_id)
        .options(
            selectinload(CodexEntry.associations),
            selectinload(CodexEntry.images),
        )
    )
    entry = result.scalar_one_or_none()
    if entry is None:
        raise HTTPException(status_code=404, detail="Codex entry not found")
    return _entry_to_response(entry)


def _sync_associations(
    entry: CodexEntry,
    work_ids: list[uuid.UUID],
    series_ids: list[uuid.UUID],
) -> None:
    assocs = []
    for wid in work_ids:
        assocs.append(CodexAssociation(
            codex_entry_id=entry.id,
            target_type="work",
            target_id=wid,
        ))
    for sid in series_ids:
        assocs.append(CodexAssociation(
            codex_entry_id=entry.id,
            target_type="series",
            target_id=sid,
        ))
    entry.associations = assocs


@router.post("/", response_model=CodexResponse, status_code=201)
async def create_codex_entry(
    data: CodexCreate,
    db: AsyncSession = Depends(get_db),
):
    entry = CodexEntry(
        entry_type=data.entry_type,
        name=data.name,
        description=data.description,
        content=data.content,
        tags=data.tags,
        metadata_=data.metadata,
        notes=data.notes,
    )
    db.add(entry)
    await db.flush()
    await db.refresh(entry, ["associations", "images"])
    _sync_associations(entry, data.work_ids, data.series_ids)
    await db.commit()
    result = await db.execute(
        select(CodexEntry)
        .where(CodexEntry.id == entry.id)
        .options(
            selectinload(CodexEntry.associations),
            selectinload(CodexEntry.images),
        )
    )
    entry = result.scalar_one()
    return _entry_to_response(entry)


@router.patch("/{entry_id}", response_model=CodexResponse)
async def update_codex_entry(
    entry_id: uuid.UUID,
    data: CodexUpdate,
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(CodexEntry)
        .where(CodexEntry.id == entry_id)
        .options(
            selectinload(CodexEntry.associations),
            selectinload(CodexEntry.images),
        )
    )
    entry = result.scalar_one_or_none()
    if entry is None:
        raise HTTPException(status_code=404, detail="Codex entry not found")

    update_data = data.model_dump(exclude_unset=True)
    work_ids = update_data.pop("work_ids", None)
    series_ids = update_data.pop("series_ids", None)

    if "metadata" in update_data:
        update_data["metadata_"] = update_data.pop("metadata")

    for key, value in update_data.items():
        setattr(entry, key, value)

    if work_ids is not None or series_ids is not None:
        current_work_ids = work_ids if work_ids is not None else [
            a.target_id for a in entry.associations if a.target_type == "work"
        ]
        current_series_ids = series_ids if series_ids is not None else [
            a.target_id for a in entry.associations if a.target_type == "series"
        ]
        _sync_associations(entry, current_work_ids, current_series_ids)

    await db.commit()
    # Re-fetch with eager loads: commit expires server-computed columns
    # (e.g. updated_at via onupdate), which would otherwise trigger a lazy
    # load during serialization outside the async context.
    result = await db.execute(
        select(CodexEntry)
        .where(CodexEntry.id == entry_id)
        .options(
            selectinload(CodexEntry.associations),
            selectinload(CodexEntry.images),
        )
    )
    entry = result.scalar_one()
    return _entry_to_response(entry)


@router.delete("/{entry_id}", status_code=204)
async def delete_codex_entry(
    entry_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(CodexEntry).where(CodexEntry.id == entry_id)
    )
    entry = result.scalar_one_or_none()
    if entry is None:
        raise HTTPException(status_code=404, detail="Codex entry not found")
    await db.delete(entry)
    await db.commit()


@router.post(
    "/{entry_id}/images", response_model=CodexImageResponse, status_code=201,
)
async def upload_codex_image(
    entry_id: uuid.UUID,
    file: UploadFile,
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(CodexEntry).where(CodexEntry.id == entry_id)
    )
    entry = result.scalar_one_or_none()
    if entry is None:
        raise HTTPException(status_code=404, detail="Codex entry not found")

    if file.content_type not in ALLOWED_TYPES:
        raise HTTPException(status_code=400, detail="File must be JPEG, PNG, WebP, or GIF")

    data = await file.read()
    if len(data) > MAX_SIZE:
        raise HTTPException(status_code=400, detail="File must be under 10 MB")

    original_name = file.filename or "image.jpg"
    ext = Path(original_name).suffix.lower() or ".jpg"
    image_id = uuid.uuid4()
    filename = f"{image_id}{ext}"

    dest_dir = UPLOAD_DIR / "codex" / str(entry_id)
    dest_dir.mkdir(parents=True, exist_ok=True)

    async with aiofiles.open(dest_dir / filename, "wb") as f:
        await f.write(data)

    width, height = _image_dimensions(data, file.content_type or "")

    is_first = not bool(entry.images)
    img = CodexImage(
        id=image_id,
        codex_entry_id=entry_id,
        filename=filename,
        original_name=original_name,
        mime_type=file.content_type or "application/octet-stream",
        size_bytes=len(data),
        width=width,
        height=height,
        is_primary=is_first,
    )
    db.add(img)
    await db.commit()
    await db.refresh(img)
    return img


@router.patch(
    "/images/{image_id}", response_model=CodexImageResponse,
)
async def update_codex_image(
    image_id: uuid.UUID,
    data: CodexImageUpdate,
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(CodexImage).where(CodexImage.id == image_id)
    )
    img = result.scalar_one_or_none()
    if img is None:
        raise HTTPException(status_code=404, detail="Image not found")

    update_data = data.model_dump(exclude_unset=True)

    if update_data.get("is_primary"):
        others = await db.execute(
            select(CodexImage).where(
                CodexImage.codex_entry_id == img.codex_entry_id,
                CodexImage.id != image_id,
            )
        )
        for other in others.scalars().all():
            other.is_primary = False

    for key, value in update_data.items():
        setattr(img, key, value)

    await db.commit()
    await db.refresh(img)
    return img


@router.delete("/images/{image_id}", status_code=204)
async def delete_codex_image(
    image_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(CodexImage).where(CodexImage.id == image_id)
    )
    img = result.scalar_one_or_none()
    if img is None:
        raise HTTPException(status_code=404, detail="Image not found")

    file_path = UPLOAD_DIR / "codex" / str(img.codex_entry_id) / img.filename
    if file_path.exists():
        file_path.unlink()

    was_primary = img.is_primary
    entry_id = img.codex_entry_id
    await db.delete(img)
    await db.flush()

    if was_primary:
        remaining = await db.execute(
            select(CodexImage)
            .where(CodexImage.codex_entry_id == entry_id)
            .order_by(CodexImage.created_at)
            .limit(1)
        )
        new_primary = remaining.scalar_one_or_none()
        if new_primary:
            new_primary.is_primary = True

    await db.commit()
