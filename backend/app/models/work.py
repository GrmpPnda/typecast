from __future__ import annotations

import enum
import uuid
from datetime import date

from sqlalchemy import JSON, Date, Enum, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import BaseModel


class WorkStatus(enum.StrEnum):
    DRAFT = "draft"
    REVISION = "revision"
    COMPLETE = "complete"
    PUBLISHED = "published"


class Work(BaseModel):
    __tablename__ = "works"

    user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=True
    )
    series_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("series.id", ondelete="SET NULL"), nullable=True
    )
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    subtitle: Mapped[str | None] = mapped_column(String(500), nullable=True)
    author: Mapped[str] = mapped_column(String(500), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    cover_image_path: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[WorkStatus] = mapped_column(Enum(WorkStatus), default=WorkStatus.DRAFT)
    isbn: Mapped[str | None] = mapped_column(String(20), nullable=True)
    genre: Mapped[list | None] = mapped_column(JSON, nullable=True, default=list)
    tags: Mapped[list | None] = mapped_column(JSON, nullable=True, default=list)
    language: Mapped[str] = mapped_column(String(10), default="en")
    publisher: Mapped[str | None] = mapped_column(String(500), nullable=True)
    publication_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    edition: Mapped[str | None] = mapped_column(String(100), nullable=True)
    word_count_target: Mapped[int | None] = mapped_column(Integer, nullable=True)
    blurb: Mapped[str | None] = mapped_column(Text, nullable=True)
    notes: Mapped[str] = mapped_column(Text, default="")
    ai_instructions: Mapped[str] = mapped_column(Text, default="")
    website: Mapped[str | None] = mapped_column(String(500), nullable=True)
    title_page_config: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    default_profile_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("profiles.id", ondelete="SET NULL"), nullable=True
    )

    series = relationship("Series", back_populates="works")
    default_profile = relationship("Profile", lazy="selectin")
    chapters = relationship(
        "Chapter", back_populates="work", lazy="selectin", cascade="all, delete-orphan"
    )
    sections = relationship(
        "Section", back_populates="work", lazy="selectin", cascade="all, delete-orphan"
    )
    images = relationship(
        "Image", back_populates="work", lazy="selectin", cascade="all, delete-orphan"
    )
