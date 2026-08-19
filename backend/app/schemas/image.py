from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel


class ImageUpdate(BaseModel):
    alt_text: str | None = None
    caption: str | None = None
    tags: str | None = None


class ImageResponse(BaseModel):
    id: uuid.UUID
    work_id: uuid.UUID
    filename: str
    original_name: str
    mime_type: str
    size_bytes: int
    width: int | None
    height: int | None
    alt_text: str
    caption: str
    tags: str = ""
    url: str
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
