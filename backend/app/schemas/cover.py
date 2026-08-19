from __future__ import annotations

from pydantic import BaseModel


class CoverDimensionsRequest(BaseModel):
    trim_width: float = 6.0
    trim_height: float = 9.0
    page_count: int = 300
    spine_factor: float = 0.0025
    cover_type: str = "paperback"
    flap_width: float = 3.5


class CoverDimensionsResponse(BaseModel):
    trim_width: float
    trim_height: float
    page_count: int
    spine_width: float
    bleed: float
    total_width: float
    total_height: float
    front_x: float
    spine_x: float
    back_x: float
    total_width_px: int
    total_height_px: int
    cover_type: str = "paperback"
    flap_width: float | None = None
    front_flap_x: float | None = None
    back_flap_x: float | None = None


class CoverGenerateRequest(BaseModel):
    trim_width: float = 6.0
    trim_height: float = 9.0
    page_count: int = 300
    spine_factor: float = 0.0025
    cover_type: str = "paperback"  # "paperback" or "hardcover"
    front_image_path: str | None = None
    back_image_path: str | None = None
    spine_text: str = ""
    back_title: str = ""
    back_blurb: str = ""
    background_color: str = "#1a1a2e"
    text_color: str = "#FFFFFF"
    spine_font_family: str | None = None
    blurb_font_family: str | None = None
    barcode_zone: bool = True
    back_overlay_opacity: int = 180
    back_logo_path: str | None = None
    back_website: str = ""
    # Hardcover dust jacket fields
    flap_width: float = 3.5
    front_flap_text: str = ""
    back_flap_text: str = ""
    # Output format
    output_format: str = "pdf"  # "pdf", "docx", or "png"
