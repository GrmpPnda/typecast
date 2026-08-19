from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel

from app.models.profile import ProfileFormat


class ProfileCreate(BaseModel):
    name: str
    format: ProfileFormat
    description: str = ""
    page_width: float | None = None
    page_height: float | None = None
    margin_top: float | None = None
    margin_bottom: float | None = None
    margin_inner: float | None = None
    margin_outer: float | None = None
    font_family: str = "Georgia, serif"
    font_size: str = "1em"
    line_height: float = 1.5
    header_footer: bool = False
    include_cover: bool = True
    include_toc: bool = True
    page_numbers: bool = False
    page_number_position: str = "center"
    page_numbers_start_at_content: bool = True
    header_recto: str | None = None
    header_verso: str | None = None
    header_position: str = "outer"
    header_font_family: str | None = None
    header_font_size: str | None = None
    header_margin_top: float | None = None
    header_from_edge: float | None = None
    footer_margin_bottom: float | None = None
    footer_from_edge: float | None = None
    footer_recto: str | None = None
    footer_verso: str | None = None
    footer_position: str = "center"
    header_font_weight: str | None = None
    front_matter_roman: bool = False
    text_align: str = "justify"
    chapter_font_family: str | None = None
    chapter_font_size: str | None = None
    chapter_font_weight: str = "normal"
    chapter_align: str = "center"
    chapter_sink: float | None = None
    chapters_start_recto: bool = False
    back_matter_page_numbers: bool = True
    extra: dict | None = None


class ProfileUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    page_width: float | None = None
    page_height: float | None = None
    margin_top: float | None = None
    margin_bottom: float | None = None
    margin_inner: float | None = None
    margin_outer: float | None = None
    font_family: str | None = None
    font_size: str | None = None
    line_height: float | None = None
    header_footer: bool | None = None
    include_cover: bool | None = None
    include_toc: bool | None = None
    page_numbers: bool | None = None
    page_number_position: str | None = None
    page_numbers_start_at_content: bool | None = None
    header_recto: str | None = None
    header_verso: str | None = None
    header_position: str | None = None
    header_font_family: str | None = None
    header_font_size: str | None = None
    header_margin_top: float | None = None
    header_from_edge: float | None = None
    footer_margin_bottom: float | None = None
    footer_from_edge: float | None = None
    footer_recto: str | None = None
    footer_verso: str | None = None
    footer_position: str | None = None
    header_font_weight: str | None = None
    front_matter_roman: bool | None = None
    text_align: str | None = None
    chapter_font_family: str | None = None
    chapter_font_size: str | None = None
    chapter_font_weight: str | None = None
    chapter_align: str | None = None
    chapter_sink: float | None = None
    chapters_start_recto: bool | None = None
    back_matter_page_numbers: bool | None = None
    extra: dict | None = None


class ProfileResponse(BaseModel):
    id: uuid.UUID
    name: str
    format: ProfileFormat
    description: str
    is_builtin: bool
    page_width: float | None
    page_height: float | None
    margin_top: float | None
    margin_bottom: float | None
    margin_inner: float | None
    margin_outer: float | None
    font_family: str
    font_size: str
    line_height: float
    header_footer: bool
    include_cover: bool
    include_toc: bool
    page_numbers: bool
    page_number_position: str
    page_numbers_start_at_content: bool
    header_recto: str | None
    header_verso: str | None
    header_position: str
    header_font_family: str | None
    header_font_size: str | None
    header_margin_top: float | None
    header_from_edge: float | None
    footer_margin_bottom: float | None
    footer_from_edge: float | None
    footer_recto: str | None
    footer_verso: str | None
    footer_position: str
    header_font_weight: str | None
    front_matter_roman: bool
    text_align: str
    chapter_font_family: str | None
    chapter_font_size: str | None
    chapter_font_weight: str | None
    chapter_align: str | None
    chapter_sink: float | None
    chapters_start_recto: bool
    back_matter_page_numbers: bool
    extra: dict | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
