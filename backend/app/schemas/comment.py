from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel


class CommentCreate(BaseModel):
    anchor_text: str = ""
    anchor_from: int = 0
    anchor_to: int = 0
    content: str = ""
    suggestion: str | None = None
    author: str = "user"


class CommentUpdate(BaseModel):
    content: str | None = None
    suggestion: str | None = None
    resolved: bool | None = None


class CommentResponse(BaseModel):
    id: uuid.UUID
    scene_id: uuid.UUID
    anchor_text: str
    anchor_from: int
    anchor_to: int
    content: str
    suggestion: str | None
    author: str
    resolved: bool
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
