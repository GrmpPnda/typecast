from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel


class ChapterCreate(BaseModel):
    title: str
    number: int | None = None
    sort_order: int = 0
    synopsis: str | None = None
    notes: str = ""
    show_title: bool = True


class ChapterUpdate(BaseModel):
    title: str | None = None
    number: int | None = None
    sort_order: int | None = None
    synopsis: str | None = None
    notes: str | None = None
    show_title: bool | None = None


class ChapterReorderItem(BaseModel):
    id: uuid.UUID
    sort_order: int
    number: int | None = None


class ChapterReorder(BaseModel):
    chapters: list[ChapterReorderItem]


class ChapterResponse(BaseModel):
    id: uuid.UUID
    work_id: uuid.UUID
    title: str
    number: int | None
    sort_order: int
    synopsis: str | None
    notes: str
    show_title: bool
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
