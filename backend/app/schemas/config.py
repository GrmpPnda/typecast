from __future__ import annotations

from pydantic import BaseModel


class ConfigEntry(BaseModel):
    key: str
    value: str
    is_secret: bool = False


class ConfigEntryResponse(BaseModel):
    key: str
    value: str
    is_secret: bool

    model_config = {"from_attributes": True}


class ConfigBulkUpdate(BaseModel):
    entries: list[ConfigEntry]
