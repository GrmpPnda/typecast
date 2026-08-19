from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.engine import get_db
from app.schemas.work import WorkResponse
from app.services.importer import import_markdown

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post("/import/markdown", response_model=WorkResponse, status_code=201)
async def import_markdown_file(
    file: UploadFile = File(...),
    title: str | None = Form(None),
    author: str | None = Form(None),
    use_ai: bool = Form(True),
    db: AsyncSession = Depends(get_db),
):
    try:
        raw = await file.read()
        content = raw.decode("utf-8")
    except UnicodeDecodeError:
        raise HTTPException(status_code=400, detail="File must be UTF-8 encoded text")

    try:
        work = await import_markdown(
            content=content,
            db=db,
            use_ai=use_ai,
            author_override=author or None,
            title_override=title or None,
        )
    except Exception:
        logger.exception("Import failed")
        raise HTTPException(status_code=500, detail="Import failed — check server logs")

    return work


@router.post("/import/paste", response_model=WorkResponse, status_code=201)
async def import_markdown_paste(
    content: str = Form(...),
    title: str | None = Form(None),
    author: str | None = Form(None),
    use_ai: bool = Form(True),
    db: AsyncSession = Depends(get_db),
):
    try:
        work = await import_markdown(
            content=content,
            db=db,
            use_ai=use_ai,
            author_override=author or None,
            title_override=title or None,
        )
    except Exception:
        logger.exception("Import failed")
        raise HTTPException(status_code=500, detail="Import failed — check server logs")

    return work
