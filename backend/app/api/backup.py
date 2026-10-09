"""Backup download, restore, and import.

All three are administrator-only. They used to have no authentication at all,
so on a multi-user deployment anyone who could reach the server could download
every manuscript and password hash, or wipe the install with a restore. In
local mode the auto-created user is an administrator, so nothing changes there.
"""

from __future__ import annotations

import io
import logging

from fastapi import APIRouter, Depends, HTTPException, UploadFile
from fastapi.responses import StreamingResponse

from app.api.deps import require_admin
from app.models.user import User
from app.services.backup import (
    BACKUP_MIME,
    BackupError,
    BackupUnsupportedError,
    Summary,
    build_backup_archive,
    import_backup_archive,
    restore_backup_archive,
)

logger = logging.getLogger(__name__)

router = APIRouter()


def summary_response(summary: Summary) -> dict:
    """The parts of a load summary the UI shows."""
    return {
        "mode": summary.mode,
        "dry_run": summary.dry_run,
        "rows": summary.rows,
        "total_rows": summary.total_rows,
        "files_written": summary.files_written,
        "files_unchanged": summary.files_unchanged,
        "file_conflicts": summary.file_conflicts,
        "profiles_remapped": summary.profiles_remapped,
        "skipped_config": summary.skipped_config,
        "secrets_dropped": summary.secrets_dropped,
        "dropped_columns": summary.dropped_columns,
    }


def _raise_for(exc: BackupError, action: str) -> None:
    if isinstance(exc, BackupUnsupportedError):
        logger.error("%s unavailable: %s", action, exc)
        raise HTTPException(status_code=501, detail=str(exc)) from exc
    logger.error("%s failed: %s", action, exc)
    raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/backup")
async def create_backup(admin: User = Depends(require_admin)):
    """Download a ZIP of every table and every upload."""
    logger.info("Backup download requested by %s", admin.email)
    try:
        data, filename = await build_backup_archive()
    except BackupError as exc:
        _raise_for(exc, "Backup")

    return StreamingResponse(
        io.BytesIO(data),
        media_type=BACKUP_MIME,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.post("/restore")
async def restore_backup(file: UploadFile, admin: User = Depends(require_admin)):
    """Replace everything with a backup's contents, accounts included."""
    logger.warning("Restore requested by %s from upload %s", admin.email, file.filename)
    content = await file.read()

    try:
        summary = await restore_backup_archive(content)
    except BackupError as exc:
        _raise_for(exc, "Restore")

    logger.info(
        "Restore succeeded (%d row(s), %d file(s))", summary.total_rows, summary.files_written
    )
    return {
        "status": "restored",
        "message": "Backup restored. Reload the application.",
        **summary_response(summary),
    }


@router.post("/import")
async def import_backup(
    file: UploadFile,
    dry_run: bool = False,
    admin: User = Depends(require_admin),
):
    """Add a backup's works to this install, owned by the signed-in account.

    For moving works between installs, including between SQLite and Postgres.
    Accounts and stored API keys are not imported.
    """
    logger.info(
        "Import requested by %s from upload %s (dry_run=%s)", admin.email, file.filename, dry_run
    )
    content = await file.read()

    try:
        summary = await import_backup_archive(content, admin.id, dry_run=dry_run)
    except BackupError as exc:
        _raise_for(exc, "Import")

    return {"status": "checked" if dry_run else "imported", **summary_response(summary)}
