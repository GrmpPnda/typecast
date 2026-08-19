from __future__ import annotations

import uuid

from sqlalchemy import Boolean, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import BaseModel


class CodexImage(BaseModel):
    __tablename__ = "codex_images"

    codex_entry_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("codex_entries.id", ondelete="CASCADE"),
    )
    filename: Mapped[str] = mapped_column(String(500))
    original_name: Mapped[str] = mapped_column(String(500))
    mime_type: Mapped[str] = mapped_column(String(100))
    size_bytes: Mapped[int] = mapped_column(Integer)
    width: Mapped[int | None] = mapped_column(Integer, nullable=True)
    height: Mapped[int | None] = mapped_column(Integer, nullable=True)
    alt_text: Mapped[str] = mapped_column(Text, default="")
    is_primary: Mapped[bool] = mapped_column(Boolean, default=False)

    entry = relationship("CodexEntry", back_populates="images")

    @property
    def url(self) -> str:
        return f"/uploads/codex/{self.codex_entry_id}/{self.filename}"
