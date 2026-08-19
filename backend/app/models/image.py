from __future__ import annotations

import uuid

from sqlalchemy import ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import BaseModel


class Image(BaseModel):
    __tablename__ = "images"

    work_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("works.id", ondelete="CASCADE"),
    )
    filename: Mapped[str] = mapped_column(String(500))
    original_name: Mapped[str] = mapped_column(String(500))
    mime_type: Mapped[str] = mapped_column(String(100))
    size_bytes: Mapped[int] = mapped_column(Integer)
    width: Mapped[int | None] = mapped_column(Integer, nullable=True)
    height: Mapped[int | None] = mapped_column(Integer, nullable=True)
    alt_text: Mapped[str] = mapped_column(Text, default="")
    caption: Mapped[str] = mapped_column(Text, default="")
    tags: Mapped[str] = mapped_column(Text, default="")

    work = relationship("Work", back_populates="images")

    @property
    def url(self) -> str:
        return f"/uploads/images/{self.work_id}/{self.filename}"
