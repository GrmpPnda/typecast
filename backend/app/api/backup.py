from __future__ import annotations

import io
import logging

from fastapi import APIRouter, HTTPException, UploadFile
from fastapi.responses import StreamingResponse

from app.services.backup import (
    BACKUP_MIME,
    BackupError,
    build_backup_archive,
    restore_backup_archive,
)

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/backup")
async def create_backup():
    """Create a ZIP containing the database and all uploads."""
    logger.info("Backup download requested")
    data, filename = await build_backup_archive()

    return StreamingResponse(
        io.BytesIO(data),
        media_type=BACKUP_MIME,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.post("/restore")
async def restore_backup(file: UploadFile):
    """Restore from a backup ZIP. Replaces database and uploads entirely."""
    logger.info("Restore requested from upload %s", file.filename)
    content = await file.read()

    try:
        restored = await restore_backup_archive(content)
    except BackupError as exc:
        logger.error("Restore failed: %s", exc)
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    logger.info("Restore succeeded (%d upload file(s))", restored)
    return {"status": "restored", "message": "Backup restored. Reload the application."}
