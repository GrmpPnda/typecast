from __future__ import annotations

import enum
import uuid

from sqlalchemy import JSON, Enum, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import BaseModel


class EntryType(enum.StrEnum):
    CHARACTER = "character"
    LOCATION = "location"
    EVENT = "event"
    SPECIES = "species"
    ITEM = "item"
    TIMELINE = "timeline"
    CUSTOM = "custom"


class CodexEntry(BaseModel):
    __tablename__ = "codex_entries"

    # The owning account. Associations link an entry to works and series, but an
    # entry created from the global codex page has none, so ownership cannot be
    # derived from them: the entry would vanish for the person who made it.
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=True, index=True
    )
    entry_type: Mapped[EntryType] = mapped_column(Enum(EntryType), nullable=False)
    name: Mapped[str] = mapped_column(String(500), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    content: Mapped[str] = mapped_column(Text, default="")
    tags: Mapped[dict | list | None] = mapped_column(JSON, nullable=True, default=list)
    metadata_: Mapped[dict | None] = mapped_column("metadata", JSON, nullable=True, default=dict)
    notes: Mapped[str] = mapped_column(Text, default="")
    voice_id: Mapped[str | None] = mapped_column(String(100), nullable=True, default=None)

    associations = relationship(
        "CodexAssociation",
        foreign_keys="CodexAssociation.codex_entry_id",
        cascade="all, delete-orphan",
        lazy="selectin",
    )
    images = relationship(
        "CodexImage",
        back_populates="entry",
        cascade="all, delete-orphan",
        lazy="selectin",
    )
