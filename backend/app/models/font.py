from __future__ import annotations

from sqlalchemy import Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import BaseModel


class Font(BaseModel):
    __tablename__ = "fonts"

    filename: Mapped[str] = mapped_column(String(500))
    original_name: Mapped[str] = mapped_column(String(500))
    family_name: Mapped[str] = mapped_column(String(300))
    style: Mapped[str] = mapped_column(String(100), default="Regular")
    mime_type: Mapped[str] = mapped_column(String(100))
    size_bytes: Mapped[int] = mapped_column(Integer)

    @property
    def url(self) -> str:
        return f"/uploads/fonts/{self.filename}"
