from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel


class ConversationCreate(BaseModel):
    work_id: uuid.UUID | None = None
    persona: str = "author"
    title: str = "New conversation"


class ConversationUpdate(BaseModel):
    title: str | None = None
    persona: str | None = None


class MessageResponse(BaseModel):
    id: uuid.UUID
    role: str
    content: str
    tool_name: str | None
    sort_order: int
    created_at: datetime

    model_config = {"from_attributes": True}


class ConversationResponse(BaseModel):
    id: uuid.UUID
    title: str
    work_id: uuid.UUID | None
    persona: str
    created_at: datetime
    updated_at: datetime
    messages: list[MessageResponse] = []

    model_config = {"from_attributes": True}


class ConversationListItem(BaseModel):
    id: uuid.UUID
    title: str
    work_id: uuid.UUID | None
    persona: str
    created_at: datetime
    updated_at: datetime
    message_count: int = 0

    model_config = {"from_attributes": True}
