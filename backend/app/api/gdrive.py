"""Google Drive endpoints: OAuth connect/disconnect plus export-to-Drive."""

from __future__ import annotations

import logging
import secrets
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import HTMLResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.config import set_config_value
from app.api.deps import require_admin
from app.db.engine import get_db
from app.models.user import User
from app.schemas.gdrive import (
    DriveAuthUrlResponse,
    DriveBackupFile,
    DriveBackupRequest,
    DriveBackupResponse,
    DriveExportRequest,
    DriveExportResponse,
    DriveRestoreRequest,
    DriveRestoreResponse,
    DriveStatusResponse,
)
from app.services import gdrive
from app.services.backup import (
    BACKUP_MIME,
    BackupError,
    BackupUnsupportedError,
    build_backup_archive,
    is_backup_filename,
    restore_backup_archive,
)
from app.services.export import (
    ExportError,
    ProfileNotFoundError,
    WorkNotFoundError,
    export_docx,
    export_epub,
    export_html,
    export_markdown,
    export_pdf,
    export_plaintext,
)

logger = logging.getLogger(__name__)

router = APIRouter()
# Google redirects the browser here after consent, so the request cannot carry a
# Bearer token. It is protected instead by the single-use OAuth state that
# /auth-url issued. Everything on ``router`` is administrator-only (app/main.py).
public_router = APIRouter()

CALLBACK_PATH = "/api/gdrive/callback"

# CSRF state for in-flight consent requests. In-memory is sufficient: the flow
# completes in one browser round trip against a local single-user server, and a
# restart mid-consent should invalidate the attempt anyway.
_pending_states: set[str] = set()


def _redirect_uri(request: Request) -> str:
    """Derive the OAuth redirect URI from the incoming request.

    The backend runs on http locally and https under ``start.sh --ssl``, so the
    URI differs between modes and both must be registered in the Google Cloud
    OAuth client. Deriving it here keeps the value shown in Settings honest.
    """
    scheme = request.url.scheme
    host = request.url.hostname or "localhost"
    port = request.url.port
    netloc = f"{host}:{port}" if port else host
    uri = f"{scheme}://{netloc}{CALLBACK_PATH}"
    logger.debug("Derived Drive redirect URI: %s", uri)
    return uri


@router.get("/status", response_model=DriveStatusResponse)
async def drive_status(
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> DriveStatusResponse:
    """Report whether Drive is configured, connected, and which account is linked."""
    creds = await gdrive.load_credentials(db)
    enabled = await gdrive.is_enabled(db)
    configured = bool(creds.client_id and creds.client_secret)
    connected = configured and bool(creds.refresh_token)

    account_email = None
    error = None
    if connected:
        try:
            account_email = await gdrive.get_account_email(creds)
        except gdrive.GoogleDriveError as exc:
            logger.warning("Drive status check failed: %s", exc)
            error = str(exc)
            connected = False

    logger.info(
        "Drive status: enabled=%s configured=%s connected=%s account=%s",
        enabled,
        configured,
        connected,
        account_email or "unknown",
    )
    return DriveStatusResponse(
        enabled=enabled,
        configured=configured,
        connected=connected,
        account_email=account_email,
        folder_id=creds.folder_id,
        redirect_uri=_redirect_uri(request),
        error=error,
    )


@router.get("/auth-url", response_model=DriveAuthUrlResponse)
async def drive_auth_url(
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> DriveAuthUrlResponse:
    """Build a consent URL for the frontend to open."""
    creds = await gdrive.load_credentials(db)
    if not creds.client_id or not creds.client_secret:
        logger.warning("Drive auth URL requested without client credentials")
        raise HTTPException(
            status_code=400,
            detail="Add a Google client ID and secret in Settings before connecting.",
        )

    state = secrets.token_urlsafe(24)
    _pending_states.add(state)
    logger.info("Issued Drive consent state (%d pending)", len(_pending_states))

    url = gdrive.build_auth_url(
        client_id=creds.client_id,
        redirect_uri=_redirect_uri(request),
        state=state,
    )
    return DriveAuthUrlResponse(auth_url=url, redirect_uri=_redirect_uri(request))


@public_router.get("/callback", response_class=HTMLResponse)
async def drive_callback(
    request: Request,
    code: str | None = Query(None),
    state: str | None = Query(None),
    error: str | None = Query(None),
    db: AsyncSession = Depends(get_db),
) -> HTMLResponse:
    """Receive the OAuth consent redirect and store the refresh token.

    Google redirects a browser here, so the response is a small HTML page rather
    than JSON.
    """
    if error:
        logger.warning("Drive consent denied: %s", error)
        return _callback_page(False, f"Google reported: {error}")

    if not code:
        logger.warning("Drive callback hit without a code")
        return _callback_page(False, "No authorisation code was returned.")

    if not state or state not in _pending_states:
        logger.warning("Drive callback with unrecognised state")
        return _callback_page(
            False,
            "This authorisation request was not recognised. Start again from Settings.",
        )
    _pending_states.discard(state)

    creds = await gdrive.load_credentials(db)
    try:
        tokens = await gdrive.exchange_code(
            code=code,
            client_id=creds.client_id,
            client_secret=creds.client_secret,
            redirect_uri=_redirect_uri(request),
        )
    except gdrive.GoogleDriveError as exc:
        logger.error("Drive code exchange failed: %s", exc)
        return _callback_page(False, str(exc))

    await set_config_value(db, "gdrive_refresh_token", tokens["refresh_token"])
    await set_config_value(db, "gdrive_enabled", "true")
    logger.info("Google Drive connected successfully")
    return _callback_page(True, "Google Drive is connected. You can close this tab.")


def _callback_page(success: bool, message: str) -> HTMLResponse:
    """Minimal standalone page for the OAuth redirect landing."""
    title = "Connected" if success else "Connection failed"
    colour = "#4ade80" if success else "#f87171"
    html = f"""<!doctype html>
<html><head><meta charset="utf-8"><title>Typecast — {title}</title></head>
<body style="background:#0a0a0b;color:#e5e7eb;font-family:system-ui,sans-serif;
             display:flex;align-items:center;justify-content:center;height:100vh;margin:0">
  <div style="text-align:center;max-width:32rem;padding:2rem">
    <h1 style="color:{colour};font-size:1.25rem;margin:0 0 .75rem">{title}</h1>
    <p style="color:#9ca3af;line-height:1.6;margin:0">{message}</p>
  </div>
  <script>if ({str(success).lower()}) setTimeout(() => window.close(), 2500);</script>
</body></html>"""
    return HTMLResponse(content=html, status_code=200)


@router.post("/disconnect", response_model=DriveStatusResponse)
async def drive_disconnect(
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> DriveStatusResponse:
    """Forget the stored refresh token and disable the integration.

    Files already in Drive are left alone; this only revokes Typecast's local
    copy of the credential.
    """
    creds = await gdrive.load_credentials(db)
    gdrive.forget_cached_token(creds.refresh_token)

    await set_config_value(db, "gdrive_refresh_token", "")
    await set_config_value(db, "gdrive_enabled", "false")
    logger.info("Google Drive disconnected")

    return await drive_status(request, db)


# --------------------------------------------------------------------------
# Export to Drive
# --------------------------------------------------------------------------

# Mirrors the download endpoint in app/api/export.py. Kept as data rather than
# branching so the two stay comparable when a format is added.
_EXPORT_MIME = {
    "markdown": "text/markdown",
    "txt": "text/plain",
    "html": "text/html",
    "pdf": "application/pdf",
    "epub": "application/epub+zip",
    "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
}


async def _render_export(
    db: AsyncSession,
    work_id: uuid.UUID,
    data: DriveExportRequest,
) -> tuple[bytes, str]:
    """Produce the export bytes and filename for the requested format."""
    fmt = data.format
    logger.debug("Rendering %s export for work %s", fmt, work_id)

    if fmt == "markdown":
        content, filename = await export_markdown(
            db, work_id, include_images=data.include_images
        )
        return content.encode("utf-8"), filename
    if fmt == "txt":
        content, filename = await export_plaintext(db, work_id)
        return content.encode("utf-8"), filename
    if fmt == "html":
        content, filename = await export_html(db, work_id)
        return content.encode("utf-8"), filename
    if fmt == "epub":
        return await export_epub(
            db, work_id, profile_id=data.profile_id, compress_images=data.compress_images
        )
    if fmt == "docx":
        return await export_docx(db, work_id, profile_id=data.profile_id)
    return await export_pdf(db, work_id, profile_id=data.profile_id)


@router.post("/works/{work_id}/export", response_model=DriveExportResponse)
async def export_work_to_drive(
    work_id: uuid.UUID,
    data: DriveExportRequest,
    db: AsyncSession = Depends(get_db),
) -> DriveExportResponse:
    """Render a work and upload it to the user's Drive.

    With ``convert_to_google_doc`` set, a convertible format (DOCX, HTML, text,
    markdown) becomes a native Google Doc so it can be read and commented on in
    the browser. PDF and ePub are always uploaded as-is.
    """
    creds = await gdrive.load_credentials(db)
    if not creds.refresh_token:
        logger.warning("Drive export attempted while disconnected")
        raise HTTPException(
            status_code=400,
            detail="Google Drive is not connected. Connect it in Settings.",
        )

    try:
        content, filename = await _render_export(db, work_id, data)
    except WorkNotFoundError:
        raise HTTPException(status_code=404, detail="Work not found")
    except ProfileNotFoundError:
        raise HTTPException(status_code=404, detail="Profile not found")
    except ExportError as exc:
        logger.error("Drive export rendering failed: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))

    mime_type = _EXPORT_MIME[data.format]
    convert = data.convert_to_google_doc and mime_type in gdrive.CONVERTIBLE_MIMES

    if data.convert_to_google_doc and not convert:
        logger.info("Format %s cannot convert to a Google Doc; uploading as-is", data.format)

    # An explicit filename wins over the title-derived one, but the extension
    # still comes from the format so the two cannot disagree.
    if data.filename:
        extension = filename.rsplit(".", 1)[-1] if "." in filename else None
        try:
            filename = gdrive.sanitize_filename(data.filename, extension=extension)
        except ValueError:
            raise HTTPException(
                status_code=400,
                detail="Filename is empty once cleaned. Use at least one ordinary character.",
            )

    # A converted upload becomes a Google Doc, so the source extension would be
    # misleading in Drive's file list.
    upload_name = filename.rsplit(".", 1)[0] if convert else filename

    segments = gdrive.split_folder_path(data.folder_path or "")
    folder_path = "/".join(segments)

    try:
        root_id = await gdrive.ensure_folder(creds)
        folder_id = await gdrive.ensure_folder_path(
            creds, folder_path, root_id=root_id
        )
        uploaded = await gdrive.upload_file(
            creds,
            content=content,
            filename=upload_name,
            mime_type=mime_type,
            folder_id=folder_id,
            convert_to_google_doc=convert,
        )
    except gdrive.NotConnectedError as exc:
        logger.error("Drive export rejected by Google: %s", exc)
        raise HTTPException(status_code=400, detail=str(exc))
    except gdrive.GoogleDriveError as exc:
        logger.error("Drive export upload failed: %s", exc)
        raise HTTPException(status_code=502, detail=str(exc))

    # Remember the top-level folder so later uploads skip the lookup. Subfolders
    # are not cached: they vary per export.
    if not creds.folder_id:
        await set_config_value(db, "gdrive_folder_id", root_id)

    logger.info(
        "Exported work %s to Drive as %s (%s, folder=%s, converted=%s)",
        work_id,
        uploaded.id,
        uploaded.mime_type,
        folder_path or "<root>",
        convert,
    )
    return DriveExportResponse(
        file_id=uploaded.id,
        name=uploaded.name,
        mime_type=uploaded.mime_type,
        web_view_link=uploaded.web_view_link,
        converted_to_google_doc=convert,
        folder_path=folder_path,
    )


async def _require_connected(db: AsyncSession) -> gdrive.DriveCredentials:
    """Load credentials, rejecting the request if Drive is not connected."""
    creds = await gdrive.load_credentials(db)
    if not creds.refresh_token:
        logger.warning("Drive operation attempted while disconnected")
        raise HTTPException(
            status_code=400,
            detail="Google Drive is not connected. Connect it in Settings.",
        )
    return creds


@router.get("/files", response_model=list[dict])
async def list_drive_files(
    db: AsyncSession = Depends(get_db),
) -> list[dict]:
    """List files Typecast has put in Drive, newest first."""
    creds = await _require_connected(db)
    try:
        files = await gdrive.list_files(creds, folder_id=creds.folder_id)
    except gdrive.NotConnectedError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except gdrive.GoogleDriveError as exc:
        logger.error("Drive file listing failed: %s", exc)
        raise HTTPException(status_code=502, detail=str(exc))

    return [
        {
            "id": f.id,
            "name": f.name,
            "mime_type": f.mime_type,
            "web_view_link": f.web_view_link,
            "size": f.size,
            "modified_time": f.modified_time,
        }
        for f in files
    ]


# --------------------------------------------------------------------------
# Backup to Drive
# --------------------------------------------------------------------------


async def _backup_folder(creds: gdrive.DriveCredentials) -> str:
    """Resolve the Backups subfolder of the Typecast folder.

    Not cached in config: it is one extra lookup, and caching a second folder id
    would mean two ways for the stored value to go stale.
    """
    parent = await gdrive.ensure_folder(creds)
    return await gdrive.ensure_folder(
        creds, gdrive.BACKUP_FOLDER_NAME, parent_id=parent
    )


async def _list_backups(creds: gdrive.DriveCredentials) -> list[gdrive.DriveFile]:
    """Archives in the Backups folder, newest first by timestamped name.

    Sorting on the name rather than modifiedTime keeps ordering stable: a Drive
    metadata touch would reorder by time but the timestamp in the name is the
    moment the archive was actually taken.
    """
    folder_id = await _backup_folder(creds)
    files = await gdrive.list_files(creds, folder_id=folder_id, mime_type=BACKUP_MIME)
    backups = [f for f in files if is_backup_filename(f.name)]
    backups.sort(key=lambda f: f.name, reverse=True)
    logger.info("Found %d Drive backup(s)", len(backups))
    return backups


@router.get("/backups", response_model=list[DriveBackupFile])
async def list_drive_backups(
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(require_admin),
) -> list[DriveBackupFile]:
    """List backup archives stored in Drive, newest first."""
    creds = await _require_connected(db)
    try:
        backups = await _list_backups(creds)
    except gdrive.NotConnectedError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except gdrive.GoogleDriveError as exc:
        logger.error("Drive backup listing failed: %s", exc)
        raise HTTPException(status_code=502, detail=str(exc))

    return [
        DriveBackupFile(
            id=f.id,
            name=f.name,
            size=f.size,
            modified_time=f.modified_time,
            web_view_link=f.web_view_link,
        )
        for f in backups
    ]


@router.post("/backup", response_model=DriveBackupResponse)
async def backup_to_drive(
    data: DriveBackupRequest,
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(require_admin),
) -> DriveBackupResponse:
    """Build a backup archive and upload it to the Drive Backups folder.

    When ``keep`` is set, older archives beyond that count are deleted after the
    new one lands. Pruning never runs before a successful upload, so a failed
    backup cannot cost the user their existing ones.
    """
    creds = await _require_connected(db)

    try:
        folder_id = await _backup_folder(creds)
    except gdrive.NotConnectedError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except gdrive.GoogleDriveError as exc:
        logger.error("Drive backup folder resolution failed: %s", exc)
        raise HTTPException(status_code=502, detail=str(exc))

    try:
        content, filename = await build_backup_archive()
    except BackupUnsupportedError as exc:
        logger.error("Drive backup unavailable: %s", exc)
        raise HTTPException(status_code=501, detail=str(exc)) from exc
    except BackupError as exc:
        logger.error("Drive backup failed: %s", exc)
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    try:
        uploaded = await gdrive.upload_file(
            creds,
            content=content,
            filename=filename,
            mime_type=BACKUP_MIME,
            folder_id=folder_id,
        )
    except gdrive.NotConnectedError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except gdrive.GoogleDriveError as exc:
        logger.error("Drive backup upload failed: %s", exc)
        raise HTTPException(status_code=502, detail=str(exc))

    pruned: list[str] = []
    if data.keep is not None:
        pruned = await _prune_backups(creds, keep=data.keep, protect_id=uploaded.id)

    logger.info(
        "Backed up to Drive as %s (%d bytes, %d pruned)",
        uploaded.id,
        len(content),
        len(pruned),
    )
    return DriveBackupResponse(
        file_id=uploaded.id,
        name=uploaded.name,
        size=len(content),
        web_view_link=uploaded.web_view_link,
        pruned=pruned,
    )


async def _prune_backups(
    creds: gdrive.DriveCredentials,
    *,
    keep: int,
    protect_id: str,
) -> list[str]:
    """Delete all but the newest ``keep`` archives.

    ``protect_id`` is the archive just uploaded; it is never deleted even if a
    clock skew put an older-looking name on it. Pruning failures are logged and
    swallowed, because the backup itself already succeeded and reporting a 502
    would wrongly suggest it did not.
    """
    pruned: list[str] = []
    try:
        backups = await _list_backups(creds)
    except gdrive.GoogleDriveError as exc:
        logger.warning("Skipping backup retention, listing failed: %s", exc)
        return pruned

    stale = [f for f in backups[keep:] if f.id != protect_id]
    if not stale:
        logger.info("Retention keep=%d: nothing to prune (%d total)", keep, len(backups))
        return pruned

    logger.info("Retention keep=%d: pruning %d archive(s)", keep, len(stale))
    for f in stale:
        try:
            await gdrive.delete_file(creds, f.id)
            pruned.append(f.name)
        except gdrive.GoogleDriveError as exc:
            logger.warning("Could not prune Drive backup %s: %s", f.name, exc)

    return pruned


@router.post("/restore", response_model=DriveRestoreResponse)
async def restore_from_drive(
    data: DriveRestoreRequest,
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(require_admin),
) -> DriveRestoreResponse:
    """Replace the local database and uploads with a Drive backup.

    Destructive and unrecoverable, so ``confirm`` must be set. Every local change
    made since the chosen archive was taken is lost.
    """
    if not data.confirm:
        logger.warning("Drive restore rejected: not confirmed")
        raise HTTPException(
            status_code=400,
            detail=(
                "Restoring replaces the local database and all uploads. "
                "Set confirm to proceed."
            ),
        )

    creds = await _require_connected(db)

    # Verify the file is one of ours before downloading. Under drive.file the app
    # can only reach files it created, but this also stops a stale UI id from
    # pointing at an exported manuscript instead of an archive.
    try:
        backups = await _list_backups(creds)
    except gdrive.NotConnectedError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except gdrive.GoogleDriveError as exc:
        logger.error("Drive restore listing failed: %s", exc)
        raise HTTPException(status_code=502, detail=str(exc))

    match = next((f for f in backups if f.id == data.file_id), None)
    if match is None:
        logger.warning("Drive restore requested for unknown archive %s", data.file_id)
        raise HTTPException(status_code=404, detail="Backup not found in Drive")

    try:
        content = await gdrive.download_file(creds, match.id)
    except gdrive.NotConnectedError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except gdrive.GoogleDriveError as exc:
        logger.error("Drive restore download failed: %s", exc)
        raise HTTPException(status_code=502, detail=str(exc))

    # Release this session's connection first. The restore disposes the engine and
    # overwrites the database file, so nothing below may touch ``db``.
    await db.close()

    try:
        summary = await restore_backup_archive(content)
    except BackupUnsupportedError as exc:
        logger.error("Drive restore unavailable: %s", exc)
        raise HTTPException(status_code=501, detail=str(exc)) from exc
    except BackupError as exc:
        logger.error("Drive restore failed: %s", exc)
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    logger.info(
        "Restored from Drive backup %s (%d row(s), %d upload file(s))",
        match.name, summary.total_rows, summary.files_written,
    )
    return DriveRestoreResponse(
        status="restored",
        name=match.name,
        files_restored=summary.files_written,
        message="Backup restored from Google Drive. Reload the application.",
    )
