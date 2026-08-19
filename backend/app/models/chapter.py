from __future__ import annotations

import uuid

from sqlalchemy import Boolean, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import BaseModel


class Chapter(BaseModel):
    __tablename__ = "chapters"

    work_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("works.id", ondelete="CASCADE"), nullable=False
    )
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    number: Mapped[int | None] = mapped_column(Integer, nullable=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    synopsis: Mapped[str | None] = mapped_column(Text, nullable=True)
    notes: Mapped[str] = mapped_column(Text, default="")
    show_title: Mapped[bool] = mapped_column(Boolean, default=True)

    work = relationship("Work", back_populates="chapters")
    scenes = relationship(
        "Scene", back_populates="chapter", lazy="selectin", cascade="all, delete-orphan"
    )
