from __future__ import annotations

import uuid
from pathlib import Path

import aiofiles
from fastapi import APIRouter, Depends, HTTPException, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from app import paths
from app.api.deps import require_admin
from app.db.engine import get_db
from app.models.font import Font
from app.repositories.sqlalchemy_repo import SQLAlchemyRepository
from app.schemas.font import FontResponse

router = APIRouter()

# Fonts are install-wide: any account may use them, only an administrator may
# add, rename, or remove one, since that changes every account's exports.
ADMIN = [Depends(require_admin)]

UPLOAD_DIR = paths.UPLOAD_DIR
ALLOWED_EXTENSIONS = {".ttf", ".otf", ".woff", ".woff2"}
MAX_SIZE = 5 * 1024 * 1024


def get_font_repo(db: AsyncSession = Depends(get_db)) -> SQLAlchemyRepository[Font]:
    return SQLAlchemyRepository(db, Font)


def _extract_font_info(data: bytes, ext: str) -> tuple[str, str]:
    """Extract family name and style from font file. Returns (family_name, style)."""
    try:
        import io

        from fontTools.ttLib import TTFont

        font = TTFont(io.BytesIO(data))
        name_table = font["name"]
        family = None
        style = "Regular"
        for record in name_table.names:
            if record.nameID == 1:
                family = record.toUnicode()
            elif record.nameID == 2:
                style = record.toUnicode()
            if family and style != "Regular":
                break
        font.close()
        return family or "Unknown", style
    except Exception:
        return Path("font").stem, "Regular"


def _mime_for_ext(ext: str) -> str:
    return {
        ".ttf": "font/ttf",
        ".otf": "font/otf",
        ".woff": "font/woff",
        ".woff2": "font/woff2",
    }.get(ext, "application/octet-stream")


@router.get("", response_model=list[FontResponse])
async def list_fonts(
    font_repo: SQLAlchemyRepository[Font] = Depends(get_font_repo),
):
    return await font_repo.get_all()


@router.post("", response_model=FontResponse, status_code=201, dependencies=ADMIN)
async def upload_font(
    file: UploadFile,
    font_repo: SQLAlchemyRepository[Font] = Depends(get_font_repo),
):
    original_name = file.filename or "font.ttf"
    ext = Path(original_name).suffix.lower()

    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"Font must be TTF, OTF, WOFF, or WOFF2 (got {ext})",
        )

    data = await file.read()
    if len(data) > MAX_SIZE:
        raise HTTPException(status_code=400, detail="Font file must be under 5 MB")

    family_name, style = _extract_font_info(data, ext)
    mime_type = _mime_for_ext(ext)

    font_id = uuid.uuid4()
    filename = f"{font_id}{ext}"

    dest_dir = UPLOAD_DIR / "fonts"
    dest_dir.mkdir(parents=True, exist_ok=True)

    async with aiofiles.open(dest_dir / filename, "wb") as f:
        await f.write(data)

    font = await font_repo.create(
        id=font_id,
        filename=filename,
        original_name=original_name,
        family_name=family_name,
        style=style,
        mime_type=mime_type,
        size_bytes=len(data),
    )
    return font


@router.put("/{font_id}", response_model=FontResponse, dependencies=ADMIN)
async def update_font(
    font_id: uuid.UUID,
    family_name: str | None = None,
    style: str | None = None,
    font_repo: SQLAlchemyRepository[Font] = Depends(get_font_repo),
):
    updates = {}
    if family_name is not None:
        updates["family_name"] = family_name
    if style is not None:
        updates["style"] = style
    if not updates:
        raise HTTPException(status_code=400, detail="No fields to update")
    font = await font_repo.update(font_id, **updates)
    if font is None:
        raise HTTPException(status_code=404, detail="Font not found")
    return font


@router.delete("/{font_id}", status_code=204, dependencies=ADMIN)
async def delete_font(
    font_id: uuid.UUID,
    font_repo: SQLAlchemyRepository[Font] = Depends(get_font_repo),
):
    font = await font_repo.get_by_id(font_id)
    if font is None:
        raise HTTPException(status_code=404, detail="Font not found")

    file_path = UPLOAD_DIR / "fonts" / font.filename
    if file_path.exists():
        file_path.unlink()

    await font_repo.delete(font_id)
