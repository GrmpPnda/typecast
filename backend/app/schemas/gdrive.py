from __future__ import annotations

import uuid
from typing import Literal

from pydantic import BaseModel, Field

ExportFormatName = Literal["markdown", "txt", "html", "pdf", "epub", "docx"]


class DriveStatusResponse(BaseModel):
    """Connection state for the Settings panel."""

    enabled: bool
    configured: bool  # client id + secret present
    connected: bool  # refresh token present and accepted
    account_email: str | None = None
    folder_id: str | None = None
    redirect_uri: str  # shown to the user for the Google Cloud console
    error: str | None = None


class DriveAuthUrlResponse(BaseModel):
    auth_url: str
    redirect_uri: str


class DriveExportRequest(BaseModel):
    format: ExportFormatName
    profile_id: uuid.UUID | None = None
    include_images: bool = False  # markdown only
    compress_images: bool = False  # ePub only
    # Convertible formats (docx, html, txt, markdown) land as a native Google Doc
    # so a reader can comment inline. Ignored for pdf and epub.
    convert_to_google_doc: bool = True
    # Destination. Both default to None, which keeps the previous behaviour: the
    # Typecast folder root and a filename derived from the work title.
    #
    # folder_path is relative to the Typecast folder and its levels are created on
    # demand. It cannot point at a pre-existing folder elsewhere in Drive: the
    # drive.file scope makes those invisible to this app.
    folder_path: str | None = Field(default=None, max_length=500)
    filename: str | None = Field(default=None, max_length=240)


class DriveExportResponse(BaseModel):
    file_id: str
    name: str
    mime_type: str
    web_view_link: str | None = None
    converted_to_google_doc: bool
    folder_path: str  # where it landed, relative to the Typecast folder


# --------------------------------------------------------------------------
# Backup to Drive
# --------------------------------------------------------------------------


class DriveBackupRequest(BaseModel):
    # Retention prunes older archives after a successful upload. None keeps
    # everything, which is the safe default for a destructive operation; the UI
    # sends an explicit number when the user opts in.
    keep: int | None = Field(default=None, ge=1, le=100)


class DriveBackupFile(BaseModel):
    id: str
    name: str
    size: int | None = None
    modified_time: str | None = None
    web_view_link: str | None = None


class DriveBackupResponse(BaseModel):
    file_id: str
    name: str
    size: int
    web_view_link: str | None = None
    pruned: list[str] = []  # names of archives deleted by retention


class DriveRestoreRequest(BaseModel):
    file_id: str
    # Replacing the local database and uploads is unrecoverable, so the caller
    # must say so explicitly rather than relying on a default.
    confirm: bool = False


class DriveRestoreResponse(BaseModel):
    status: str
    name: str
    files_restored: int
    message: str
