from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel


class SeriesCreate(BaseModel):
    title: str
    description: str | None = None
    cover_image_path: str | None = None
    sort_order: int = 0
    ai_instructions: str = ""


class SeriesUpdate(BaseModel):
    title: str | None = None
    description: str | None = None
    cover_image_path: str | None = None
    sort_order: int | None = None
    ai_instructions: str | None = None


class SeriesResponse(BaseModel):
    id: uuid.UUID
    title: str
    description: str | None
    cover_image_path: str | None
    sort_order: int
    ai_instructions: str
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
