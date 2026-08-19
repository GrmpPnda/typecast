from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel

from app.models.scene import SceneStatus


class SceneCreate(BaseModel):
    title: str | None = None
    sort_order: int = 0
    status: SceneStatus = SceneStatus.OUTLINE
    pov_character: str | None = None
    content: str = ""
    notes: str = ""


class SceneUpdate(BaseModel):
    title: str | None = None
    sort_order: int | None = None
    status: SceneStatus | None = None
    pov_character: str | None = None
    content: str | None = None
    notes: str | None = None


class SceneResponse(BaseModel):
    id: uuid.UUID
    chapter_id: uuid.UUID
    title: str | None
    sort_order: int
    word_count: int
    status: SceneStatus
    pov_character: str | None
    content: str
    notes: str
    checkpoint: str | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
