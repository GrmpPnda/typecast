from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel

from app.models.codex import EntryType
from app.schemas.codex_image import CodexImageResponse


class CodexCreate(BaseModel):
    entry_type: EntryType
    name: str
    description: str | None = None
    content: str = ""
    tags: list[str] = []
    metadata: dict[str, Any] = {}
    notes: str = ""
    voice_id: str | None = None
    work_ids: list[uuid.UUID] = []
    series_ids: list[uuid.UUID] = []


class CodexUpdate(BaseModel):
    entry_type: EntryType | None = None
    name: str | None = None
    description: str | None = None
    content: str | None = None
    tags: list[str] | None = None
    metadata: dict[str, Any] | None = None
    notes: str | None = None
    voice_id: str | None = None
    work_ids: list[uuid.UUID] | None = None
    series_ids: list[uuid.UUID] | None = None


class CodexResponse(BaseModel):
    id: uuid.UUID
    entry_type: EntryType
    name: str
    description: str | None
    content: str
    tags: list[str] | None
    metadata: dict[str, Any] | None
    notes: str
    voice_id: str | None = None
    work_ids: list[uuid.UUID] = []
    series_ids: list[uuid.UUID] = []
    images: list[CodexImageResponse] = []
    primary_image_url: str | None = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
