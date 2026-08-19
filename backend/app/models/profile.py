from __future__ import annotations

import enum

from sqlalchemy import JSON, Boolean, Enum, Float, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import BaseModel


class ProfileFormat(enum.StrEnum):
    PDF = "pdf"
    EPUB = "epub"


class PageNumberPosition(enum.StrEnum):
    CENTER = "center"
    LEFT = "left"
    RIGHT = "right"
    OUTSIDE = "outside"


class Profile(BaseModel):
    __tablename__ = "profiles"

    name: Mapped[str] = mapped_column(String(200), nullable=False)
    format: Mapped[ProfileFormat] = mapped_column(Enum(ProfileFormat), nullable=False)
    description: Mapped[str] = mapped_column(Text, default="")
    is_builtin: Mapped[bool] = mapped_column(Boolean, default=False)

    page_width: Mapped[float | None] = mapped_column(Float, nullable=True)
    page_height: Mapped[float | None] = mapped_column(Float, nullable=True)
    margin_top: Mapped[float | None] = mapped_column(Float, nullable=True)
    margin_bottom: Mapped[float | None] = mapped_column(Float, nullable=True)
    margin_inner: Mapped[float | None] = mapped_column(Float, nullable=True)
    margin_outer: Mapped[float | None] = mapped_column(Float, nullable=True)
    font_family: Mapped[str] = mapped_column(String(200), default="Georgia, serif")
    font_size: Mapped[str] = mapped_column(String(20), default="1em")
    line_height: Mapped[float] = mapped_column(Float, default=1.5)
    header_footer: Mapped[bool] = mapped_column(Boolean, default=False)
    include_cover: Mapped[bool] = mapped_column(Boolean, default=True)
    include_toc: Mapped[bool] = mapped_column(Boolean, default=True)
    page_numbers: Mapped[bool] = mapped_column(Boolean, default=False)
    page_number_position: Mapped[str] = mapped_column(String(20), default="center")
    page_numbers_start_at_content: Mapped[bool] = mapped_column(Boolean, default=True)
    header_recto: Mapped[str | None] = mapped_column(String(50), nullable=True)
    header_verso: Mapped[str | None] = mapped_column(String(50), nullable=True)
    header_position: Mapped[str] = mapped_column(String(20), default="outer")
    text_align: Mapped[str] = mapped_column(String(20), default="justify")
    header_font_family: Mapped[str | None] = mapped_column(String(200), nullable=True)
    header_font_size: Mapped[str | None] = mapped_column(String(20), nullable=True)
    header_margin_top: Mapped[float | None] = mapped_column(Float, nullable=True)
    header_from_edge: Mapped[float | None] = mapped_column(Float, nullable=True)
    footer_margin_bottom: Mapped[float | None] = mapped_column(Float, nullable=True)
    footer_from_edge: Mapped[float | None] = mapped_column(Float, nullable=True)
    footer_recto: Mapped[str | None] = mapped_column(String(50), nullable=True)
    footer_verso: Mapped[str | None] = mapped_column(String(50), nullable=True)
    footer_position: Mapped[str] = mapped_column(String(20), default="center")
    header_font_weight: Mapped[str | None] = mapped_column(String(20), nullable=True)
    front_matter_roman: Mapped[bool] = mapped_column(Boolean, default=False)
    chapter_font_family: Mapped[str | None] = mapped_column(String(200), nullable=True)
    chapter_font_size: Mapped[str | None] = mapped_column(String(20), nullable=True)
    chapter_font_weight: Mapped[str | None] = mapped_column(String(20), nullable=True)
    chapter_align: Mapped[str | None] = mapped_column(String(20), nullable=True)
    chapter_sink: Mapped[float | None] = mapped_column(Float, nullable=True)
    chapters_start_recto: Mapped[bool] = mapped_column(Boolean, default=False)
    back_matter_page_numbers: Mapped[bool] = mapped_column(Boolean, default=True)
    extra: Mapped[dict | None] = mapped_column(JSON, nullable=True)
