from __future__ import annotations

import uuid
from datetime import date, datetime

from pydantic import BaseModel

from app.models.work import WorkStatus


class WorkCreate(BaseModel):
    series_id: uuid.UUID | None = None
    title: str
    subtitle: str | None = None
    author: str
    description: str | None = None
    cover_image_path: str | None = None
    sort_order: int = 0
    status: WorkStatus = WorkStatus.DRAFT
    isbn: str | None = None
    genre: list[str] = []
    tags: list[str] = []
    language: str = "en"
    publisher: str | None = None
    publication_date: date | None = None
    edition: str | None = None
    word_count_target: int | None = None
    blurb: str | None = None
    website: str | None = None
    notes: str = ""
    ai_instructions: str = ""
    title_page_config: dict | None = None
    default_profile_id: uuid.UUID | None = None


class WorkUpdate(BaseModel):
    series_id: uuid.UUID | None = None
    title: str | None = None
    subtitle: str | None = None
    author: str | None = None
    description: str | None = None
    cover_image_path: str | None = None
    sort_order: int | None = None
    status: WorkStatus | None = None
    isbn: str | None = None
    genre: list[str] | None = None
    tags: list[str] | None = None
    language: str | None = None
    publisher: str | None = None
    publication_date: date | None = None
    edition: str | None = None
    word_count_target: int | None = None
    blurb: str | None = None
    website: str | None = None
    notes: str | None = None
    ai_instructions: str | None = None
    title_page_config: dict | None = None
    default_profile_id: uuid.UUID | None = None


class WorkResponse(BaseModel):
    id: uuid.UUID
    series_id: uuid.UUID | None
    title: str
    subtitle: str | None
    author: str
    description: str | None
    cover_image_path: str | None
    sort_order: int
    status: WorkStatus
    isbn: str | None
    genre: list[str] | None
    tags: list[str] | None
    language: str
    publisher: str | None
    publication_date: date | None
    edition: str | None
    word_count_target: int | None
    blurb: str | None
    website: str | None
    notes: str
    ai_instructions: str
    title_page_config: dict | None
    default_profile_id: uuid.UUID | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
