from __future__ import annotations

import enum
import uuid

from sqlalchemy import Enum, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import BaseModel


class SceneStatus(enum.StrEnum):
    OUTLINE = "outline"
    DRAFT = "draft"
    REVISION = "revision"
    FINAL = "final"


class Scene(BaseModel):
    __tablename__ = "scenes"

    chapter_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("chapters.id", ondelete="CASCADE"), nullable=False
    )
    title: Mapped[str | None] = mapped_column(String(500), nullable=True)
    content: Mapped[str] = mapped_column(Text, default="")
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    word_count: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[SceneStatus] = mapped_column(Enum(SceneStatus), default=SceneStatus.OUTLINE)
    pov_character: Mapped[str | None] = mapped_column(String(200), nullable=True)

    notes: Mapped[str] = mapped_column(Text, default="")
    checkpoint: Mapped[str | None] = mapped_column(Text, nullable=True, default=None)

    chapter = relationship("Chapter", back_populates="scenes")
    comments = relationship("Comment", back_populates="scene", cascade="all, delete-orphan")
