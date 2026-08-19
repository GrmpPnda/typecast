from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel

from app.models.section import SectionPlacement, SectionType


class SectionCreate(BaseModel):
    section_type: SectionType
    placement: SectionPlacement
    title: str | None = None
    content: str = ""
    notes: str = ""
    sort_order: int = 0
    include_in_toc: bool = False
    include_page_numbers: bool = False
    start_recto: bool = True


class SectionUpdate(BaseModel):
    section_type: SectionType | None = None
    placement: SectionPlacement | None = None
    title: str | None = None
    content: str | None = None
    notes: str | None = None
    sort_order: int | None = None
    include_in_toc: bool | None = None
    include_page_numbers: bool | None = None
    start_recto: bool | None = None


class SectionResponse(BaseModel):
    id: uuid.UUID
    work_id: uuid.UUID
    section_type: SectionType
    placement: SectionPlacement
    title: str | None
    content: str
    notes: str
    sort_order: int
    include_in_toc: bool
    include_page_numbers: bool
    start_recto: bool
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
