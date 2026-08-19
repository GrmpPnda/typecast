from __future__ import annotations

import uuid

from sqlalchemy import ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import BaseModel


class Series(BaseModel):
    __tablename__ = "series"

    user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=True
    )
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    cover_image_path: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    ai_instructions: Mapped[str] = mapped_column(Text, default="")

    owner = relationship("User", lazy="selectin")
    works = relationship("Work", back_populates="series", lazy="selectin")
