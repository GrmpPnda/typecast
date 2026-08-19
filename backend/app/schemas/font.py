from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel


class FontResponse(BaseModel):
    id: uuid.UUID
    filename: str
    original_name: str
    family_name: str
    style: str
    mime_type: str
    size_bytes: int
    url: str
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
