from __future__ import annotations

import uuid
from enum import StrEnum

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.engine import get_db
from app.services.export import (
    ExportError,
    ProfileNotFoundError,
    WorkNotFoundError,
    export_docx,
    export_epub,
    export_html,
    export_markdown,
    export_pdf,
    export_plaintext,
)

router = APIRouter()


class ExportFormat(StrEnum):
    MARKDOWN = "markdown"
    TXT = "txt"
    HTML = "html"
    PDF = "pdf"
    EPUB = "epub"
    DOCX = "docx"


@router.get("/works/{work_id}/export")
async def export_work(
    work_id: uuid.UUID,
    format: ExportFormat = Query(..., description="Export format"),
    profile_id: uuid.UUID | None = Query(None, description="Profile ID for styling"),
    include_images: bool = Query(False, description="Include image tags in markdown export"),
    compress_images: bool = Query(False, description="Compress images for smaller ePub"),
    db: AsyncSession = Depends(get_db),
) -> Response:
    try:
        if format == ExportFormat.MARKDOWN:
            content, filename = await export_markdown(db, work_id, include_images=include_images)
            return Response(
                content=content.encode("utf-8"),
                media_type="text/markdown; charset=utf-8",
                headers={"Content-Disposition": f'attachment; filename="{filename}"'},
            )

        if format == ExportFormat.TXT:
            content, filename = await export_plaintext(db, work_id)
            return Response(
                content=content.encode("utf-8"),
                media_type="text/plain; charset=utf-8",
                headers={"Content-Disposition": f'attachment; filename="{filename}"'},
            )

        if format == ExportFormat.HTML:
            content, filename = await export_html(db, work_id)
            return Response(
                content=content.encode("utf-8"),
                media_type="text/html; charset=utf-8",
                headers={"Content-Disposition": f'attachment; filename="{filename}"'},
            )

        if format == ExportFormat.EPUB:
            epub_bytes, filename = await export_epub(
                db, work_id, profile_id=profile_id, compress_images=compress_images,
            )
            return Response(
                content=epub_bytes,
                media_type="application/epub+zip",
                headers={"Content-Disposition": f'attachment; filename="{filename}"'},
            )

        if format == ExportFormat.DOCX:
            docx_bytes, filename = await export_docx(db, work_id, profile_id=profile_id)
            return Response(
                content=docx_bytes,
                media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                headers={"Content-Disposition": f'attachment; filename="{filename}"'},
            )

        # PDF
        pdf_bytes, filename = await export_pdf(db, work_id, profile_id=profile_id)
        return Response(
            content=pdf_bytes,
            media_type="application/pdf",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )

    except WorkNotFoundError:
        raise HTTPException(status_code=404, detail="Work not found")
    except ProfileNotFoundError:
        raise HTTPException(status_code=404, detail="Profile not found")
    except ExportError as exc:
        raise HTTPException(status_code=500, detail=str(exc))
