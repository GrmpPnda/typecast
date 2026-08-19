from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel


class GalleryItem(BaseModel):
    """A unified image record spanning work galleries, covers, and codex images."""

    id: str  # source-prefixed id, e.g. "image:<uuid>", "cover:<work_id>", "codex:<uuid>"
    source: str  # "gallery" | "cover" | "codex"
    url: str
    original_name: str
    mime_type: str | None = None
    size_bytes: int | None = None
    width: int | None = None
    height: int | None = None
    alt_text: str = ""
    tags: str = ""
    # Provenance
    work_id: uuid.UUID | None = None
    work_title: str | None = None
    codex_entry_id: uuid.UUID | None = None
    codex_entry_name: str | None = None
    # Whether this item supports management actions (rename/tag/reassign/delete)
    manageable: bool = False
    created_at: datetime | None = None


class ReassignRequest(BaseModel):
    work_id: uuid.UUID


class BulkDeleteRequest(BaseModel):
    image_ids: list[uuid.UUID]


class GalleryImageUpdate(BaseModel):
    alt_text: str | None = None
    tags: str | None = None
