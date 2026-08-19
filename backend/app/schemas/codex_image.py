from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel


class CodexImageResponse(BaseModel):
    id: uuid.UUID
    codex_entry_id: uuid.UUID
    filename: str
    original_name: str
    mime_type: str
    size_bytes: int
    width: int | None
    height: int | None
    alt_text: str
    is_primary: bool
    url: str
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class CodexImageUpdate(BaseModel):
    alt_text: str | None = None
    is_primary: bool | None = None
