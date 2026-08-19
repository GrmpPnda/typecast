from __future__ import annotations

import uuid

from pydantic import BaseModel


class Mention(BaseModel):
    type: str  # "codex", "chapter", "scene", "work"
    id: uuid.UUID


class ImageAttachment(BaseModel):
    data: str  # base64-encoded image data
    mime_type: str  # e.g. "image/png", "image/jpeg"
    name: str = ""  # optional display name


class AIChatRequest(BaseModel):
    prompt: str
    work_id: uuid.UUID | None = None
    chapter_id: uuid.UUID | None = None
    scene_id: uuid.UUID | None = None
    conversation_id: uuid.UUID | None = None
    persona: str | None = None
    mentions: list[Mention] = []
    attachments: list[ImageAttachment] = []
