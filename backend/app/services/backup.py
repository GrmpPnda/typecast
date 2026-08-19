"""Backup archive construction and restoration.

Extracted from ``app/api/backup.py`` so the local download/upload endpoints and
the Google Drive backup endpoints build and consume byte-identical archives.
"""

from __future__ import annotations

import io
import logging
import shutil
import zipfile
from datetime import UTC, datetime

from sqlalchemy import text

from app import paths
from app.db.engine import engine

logger = logging.getLogger(__name__)

# Re-exported for callers and tests that already import them from here. The
# resolution itself lives in app.paths so every upload path agrees.
BACKEND_DIR = paths.BACKEND_DIR
resolve_data_dir = paths.resolve_data_dir

DATA_DIR = paths.DATA_DIR
DB_PATH = paths.DB_PATH
UPLOAD_DIR = paths.UPLOAD_DIR

ARCHIVE_DB_NAME = "typecast.db"
BACKUP_PREFIX = "typecast-backup-"
BACKUP_MIME = "application/zip"


class BackupError(Exception):
    """Archive could not be built or read."""


def backup_filename(now: datetime | None = None) -> str:
    """Timestamped archive name. Also the retention sort key in Drive."""
    stamp = (now or datetime.now(UTC)).strftime("%Y%m%d-%H%M%S")
    return f"{BACKUP_PREFIX}{stamp}.zip"


def is_backup_filename(name: str) -> bool:
    """Whether a Drive filename looks like one of our archives.

    Retention deletes files, so this gates which ones are eligible; anything the
    user dropped in the folder by hand must not match.
    """
    return name.startswith(BACKUP_PREFIX) and name.endswith(".zip")


async def build_backup_archive() -> tuple[bytes, str]:
    """Build a ZIP of the database plus every upload.

    Returns the archive bytes and its filename.
    """
    logger.info("Building backup archive (db=%s, uploads=%s)", DB_PATH, UPLOAD_DIR)

    # Checkpoint the WAL so the copied database file is a consistent snapshot.
    async with engine.begin() as conn:
        await conn.execute(text("PRAGMA wal_checkpoint(TRUNCATE)"))

    buf = io.BytesIO()
    file_count = 0
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        if DB_PATH.exists():
            zf.write(DB_PATH, ARCHIVE_DB_NAME)
        else:
            logger.warning("Database file missing at %s; archive will have no DB", DB_PATH)

        if UPLOAD_DIR.exists():
            for file in UPLOAD_DIR.rglob("*"):
                if file.is_file():
                    zf.write(file, f"uploads/{file.relative_to(UPLOAD_DIR)}")
                    file_count += 1

    data = buf.getvalue()
    filename = backup_filename()
    logger.info(
        "Built backup archive %s (%d bytes, %d upload file(s))",
        filename,
        len(data),
        file_count,
    )
    return data, filename


async def restore_backup_archive(content: bytes) -> int:
    """Replace the database and uploads from an archive.

    Destructive by design: the uploads directory is removed and rebuilt. Returns
    the number of upload files restored.
    """
    logger.info("Restoring from backup archive (%d bytes)", len(content))

    try:
        with zipfile.ZipFile(io.BytesIO(content), "r") as zf:
            names = zf.namelist()
            if ARCHIVE_DB_NAME not in names:
                logger.error("Archive is missing %s", ARCHIVE_DB_NAME)
                raise BackupError(f"Invalid backup: missing {ARCHIVE_DB_NAME}")

            # Close pooled connections before overwriting the database file.
            await engine.dispose()

            DB_PATH.parent.mkdir(parents=True, exist_ok=True)
            DB_PATH.write_bytes(zf.read(ARCHIVE_DB_NAME))

            if UPLOAD_DIR.exists():
                shutil.rmtree(UPLOAD_DIR)
            UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

            restored = 0
            for name in names:
                if name.startswith("uploads/") and not name.endswith("/"):
                    # Guard against path traversal in a hand-edited archive.
                    dest = (DATA_DIR / name).resolve()
                    if not str(dest).startswith(str(UPLOAD_DIR.resolve())):
                        logger.warning("Skipping suspicious archive entry: %s", name)
                        continue
                    dest.parent.mkdir(parents=True, exist_ok=True)
                    dest.write_bytes(zf.read(name))
                    restored += 1

    except zipfile.BadZipFile as exc:
        logger.error("Archive is not a valid ZIP: %s", exc)
        raise BackupError("Invalid ZIP file") from exc

    logger.info("Restore complete (%d upload file(s))", restored)
    return restored
