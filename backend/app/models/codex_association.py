from __future__ import annotations

import uuid

from sqlalchemy import ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import BaseModel


class CodexAssociation(BaseModel):
    __tablename__ = "codex_associations"

    codex_entry_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("codex_entries.id", ondelete="CASCADE"), nullable=False
    )
    target_type: Mapped[str] = mapped_column(String(20), nullable=False)
    target_id: Mapped[uuid.UUID] = mapped_column(nullable=False)
