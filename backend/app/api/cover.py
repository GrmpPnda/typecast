from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.engine import get_db
from app.models.work import Work
from app.repositories.sqlalchemy_repo import SQLAlchemyRepository
from app.schemas.cover import (
    CoverDimensionsRequest,
    CoverDimensionsResponse,
    CoverGenerateRequest,
)
from app.services.cover import calculate_dimensions, generate_cover_docx, generate_full_cover

router = APIRouter()


@router.post("/dimensions", response_model=CoverDimensionsResponse)
async def get_cover_dimensions(data: CoverDimensionsRequest):
    dims = calculate_dimensions(
        trim_width=data.trim_width,
        trim_height=data.trim_height,
        page_count=data.page_count,
        spine_factor=data.spine_factor,
        cover_type=data.cover_type,
        flap_width=data.flap_width,
    )
    return dims.to_dict()


@router.post("/{work_id}/generate")
async def generate_cover(
    work_id: uuid.UUID,
    data: CoverGenerateRequest,
    db: AsyncSession = Depends(get_db),
):
    repo = SQLAlchemyRepository(db, Work)
    work = await repo.get_by_id(work_id)
    if work is None:
        raise HTTPException(status_code=404, detail="Work not found")

    dims = calculate_dimensions(
        trim_width=data.trim_width,
        trim_height=data.trim_height,
        page_count=data.page_count,
        spine_factor=data.spine_factor,
        cover_type=data.cover_type,
        flap_width=data.flap_width,
    )

    front_path = data.front_image_path or work.cover_image_path
    spine = data.spine_text or work.title
    title = data.back_title or work.title
    blurb = data.back_blurb or work.blurb or ""

    if data.output_format == "docx":
        buf = generate_cover_docx(
            dims=dims,
            front_image_path=front_path,
            back_image_path=data.back_image_path,
            spine_text=spine,
            back_title=title,
            back_blurb=blurb,
            background_color=data.background_color,
            text_color=data.text_color,
            spine_font_family=data.spine_font_family,
            blurb_font_family=data.blurb_font_family,
            back_website=data.back_website,
            front_flap_text=data.front_flap_text,
            back_flap_text=data.back_flap_text,
        )
        filename = f"{work.title or 'cover'}_full_cover.docx"
        return StreamingResponse(
            buf,
            media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )

    png_buf = generate_full_cover(
        dims=dims,
        front_image_path=front_path,
        back_image_path=data.back_image_path,
        spine_text=spine,
        back_title=title,
        back_blurb=blurb,
        background_color=data.background_color,
        text_color=data.text_color,
        spine_font_family=data.spine_font_family,
        blurb_font_family=data.blurb_font_family,
        barcode_zone=data.barcode_zone,
        back_overlay_opacity=data.back_overlay_opacity,
        back_logo_path=data.back_logo_path,
        back_website=data.back_website,
        front_flap_text=data.front_flap_text,
        back_flap_text=data.back_flap_text,
    )

    if data.output_format == "png":
        filename = f"{work.title or 'cover'}_full_cover.png"
        return StreamingResponse(
            png_buf,
            media_type="image/png",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )

    # Default: PDF — embed the rendered PNG at exact physical dimensions
    from app.services.cover import generate_cover_pdf

    pdf_buf = generate_cover_pdf(png_buf, dims)
    filename = f"{work.title or 'cover'}_full_cover.pdf"
    return StreamingResponse(
        pdf_buf,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.post("/{work_id}/preview")
async def preview_cover(
    work_id: uuid.UUID,
    data: CoverGenerateRequest,
    db: AsyncSession = Depends(get_db),
):
    repo = SQLAlchemyRepository(db, Work)
    work = await repo.get_by_id(work_id)
    if work is None:
        raise HTTPException(status_code=404, detail="Work not found")

    dims = calculate_dimensions(
        trim_width=data.trim_width,
        trim_height=data.trim_height,
        page_count=data.page_count,
        spine_factor=data.spine_factor,
        cover_type=data.cover_type,
        flap_width=data.flap_width,
    )

    front_path = data.front_image_path or work.cover_image_path
    buf = generate_full_cover(
        dims=dims,
        front_image_path=front_path,
        back_image_path=data.back_image_path,
        spine_text=data.spine_text or work.title,
        back_title=data.back_title or work.title,
        back_blurb=data.back_blurb or work.blurb or "",
        background_color=data.background_color,
        text_color=data.text_color,
        spine_font_family=data.spine_font_family,
        blurb_font_family=data.blurb_font_family,
        barcode_zone=data.barcode_zone,
        back_overlay_opacity=data.back_overlay_opacity,
        back_website=data.back_website,
        front_flap_text=data.front_flap_text,
        back_flap_text=data.back_flap_text,
        draw_guides=True,
    )

    return StreamingResponse(buf, media_type="image/png")
