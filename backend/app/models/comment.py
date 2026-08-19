from __future__ import annotations

import uuid

from sqlalchemy import Boolean, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import BaseModel


class Comment(BaseModel):
    __tablename__ = "comments"

    scene_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("scenes.id", ondelete="CASCADE"), nullable=False
    )
    anchor_text: Mapped[str] = mapped_column(Text, default="")
    anchor_from: Mapped[int] = mapped_column(Integer, default=0)
    anchor_to: Mapped[int] = mapped_column(Integer, default=0)
    content: Mapped[str] = mapped_column(Text, default="")
    suggestion: Mapped[str | None] = mapped_column(Text, nullable=True, default=None)
    author: Mapped[str] = mapped_column(String(200), default="user")
    resolved: Mapped[bool] = mapped_column(Boolean, default=False)

    scene = relationship("Scene", back_populates="comments")
