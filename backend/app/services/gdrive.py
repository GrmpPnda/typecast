"""Google Drive integration.

Bring-your-own-credentials OAuth2 installed-app flow. The user supplies a client
ID/secret from their own Google Cloud project; Typecast stores both encrypted
alongside the AI API keys and exchanges the consent code for a refresh token.

Scope is deliberately limited to ``drive.file`` — access only to files this app
creates. That keeps the OAuth client in a non-sensitive scope tier (no Google
verification review needed), at the cost of being unable to browse pre-existing
Drive content. See CLAUDE.md for the full rationale.

REST calls are hand-rolled over httpx rather than pulling in
google-api-python-client + google-auth-oauthlib, which would be three heavy
dependencies for a token refresh and a multipart upload.
"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass
from urllib.parse import urlencode

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

AUTH_ENDPOINT = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_ENDPOINT = "https://oauth2.googleapis.com/token"
UPLOAD_ENDPOINT = "https://www.googleapis.com/upload/drive/v3/files"
FILES_ENDPOINT = "https://www.googleapis.com/drive/v3/files"
USERINFO_ENDPOINT = "https://www.googleapis.com/oauth2/v3/userinfo"

# drive.file: per-file access to files created by this app. Non-sensitive tier.
SCOPES = [
    "https://www.googleapis.com/auth/drive.file",
    "https://www.googleapis.com/auth/userinfo.email",
]

FOLDER_MIME = "application/vnd.google-apps.folder"
GOOGLE_DOC_MIME = "application/vnd.google-apps.document"

DEFAULT_FOLDER_NAME = "Typecast"
# Backups live in a subfolder so the export folder stays readable.
BACKUP_FOLDER_NAME = "Backups"
REQUEST_TIMEOUT = 120.0

# Drive's own limit is 32767 bytes; this keeps names manageable everywhere else.
MAX_NAME_LENGTH = 240

# Formats Drive can convert into a native Google editor file on upload.
CONVERTIBLE_MIMES = {
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": GOOGLE_DOC_MIME,
    "text/html": GOOGLE_DOC_MIME,
    "text/plain": GOOGLE_DOC_MIME,
    "text/markdown": GOOGLE_DOC_MIME,
}


class GoogleDriveError(Exception):
    """Any Drive interaction failure surfaced to the caller."""


class NotConnectedError(GoogleDriveError):
    """Drive is not configured, or the stored refresh token is gone."""


@dataclass
class DriveFile:
    """A file as returned by the Drive API."""

    id: str
    name: str
    mime_type: str
    web_view_link: str | None = None
    size: int | None = None
    modified_time: str | None = None

    @classmethod
    def from_api(cls, payload: dict) -> DriveFile:
        size = payload.get("size")
        return cls(
            id=payload["id"],
            name=payload.get("name", ""),
            mime_type=payload.get("mimeType", ""),
            web_view_link=payload.get("webViewLink"),
            size=int(size) if size is not None else None,
            modified_time=payload.get("modifiedTime"),
        )


# --------------------------------------------------------------------------
# Credentials
# --------------------------------------------------------------------------


@dataclass
class DriveCredentials:
    client_id: str
    client_secret: str
    refresh_token: str | None
    folder_id: str | None


async def load_credentials(db: AsyncSession) -> DriveCredentials:
    """Read Drive credentials out of app config (secrets are decrypted)."""
    from app.api.config import get_config_value

    client_id = (await get_config_value(db, "gdrive_client_id")).strip()
    client_secret = (await get_config_value(db, "gdrive_client_secret")).strip()
    refresh_token = (await get_config_value(db, "gdrive_refresh_token")).strip()
    folder_id = (await get_config_value(db, "gdrive_folder_id")).strip()

    logger.debug(
        "Loaded Drive credentials: client_id=%s, has_secret=%s, has_refresh=%s, folder=%s",
        "set" if client_id else "unset",
        bool(client_secret),
        bool(refresh_token),
        folder_id or "unset",
    )
    return DriveCredentials(
        client_id=client_id,
        client_secret=client_secret,
        refresh_token=refresh_token or None,
        folder_id=folder_id or None,
    )


async def is_enabled(db: AsyncSession) -> bool:
    """True when the user has switched the integration on."""
    from app.api.config import get_config_value

    value = (await get_config_value(db, "gdrive_enabled")).strip().lower()
    return value == "true"


# --------------------------------------------------------------------------
# OAuth flow
# --------------------------------------------------------------------------


def build_auth_url(client_id: str, redirect_uri: str, state: str) -> str:
    """Build the consent URL for the installed-app flow.

    ``access_type=offline`` plus ``prompt=consent`` is what makes Google return a
    refresh token; without the prompt, a repeat authorisation yields only an
    access token and reconnecting would appear to succeed but store nothing.
    """
    params = {
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": " ".join(SCOPES),
        "access_type": "offline",
        "prompt": "consent",
        "include_granted_scopes": "true",
        "state": state,
    }
    url = f"{AUTH_ENDPOINT}?{urlencode(params)}"
    logger.info("Built Drive consent URL (redirect_uri=%s)", redirect_uri)
    return url


async def exchange_code(
    code: str,
    client_id: str,
    client_secret: str,
    redirect_uri: str,
) -> dict:
    """Trade a consent code for access + refresh tokens."""
    logger.info("Exchanging Drive consent code for tokens")
    payload = {
        "code": code,
        "client_id": client_id,
        "client_secret": client_secret,
        "redirect_uri": redirect_uri,
        "grant_type": "authorization_code",
    }
    async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT) as http:
        response = await http.post(TOKEN_ENDPOINT, data=payload)

    if response.status_code != 200:
        logger.error(
            "Drive code exchange failed: status=%s body=%s",
            response.status_code,
            response.text[:500],
        )
        raise GoogleDriveError(_describe_token_error(response))

    tokens = response.json()
    if not tokens.get("refresh_token"):
        logger.error("Drive code exchange returned no refresh token")
        raise GoogleDriveError(
            "Google did not return a refresh token. Revoke Typecast's access in "
            "your Google account settings and connect again."
        )
    logger.info("Drive code exchange succeeded")
    return tokens


# Access tokens live an hour; cache per refresh token to avoid a round trip on
# every upload. Keyed by refresh token so revoking invalidates the entry.
_token_cache: dict[str, tuple[str, float]] = {}


async def get_access_token(creds: DriveCredentials) -> str:
    """Return a valid access token, refreshing when the cached one is stale."""
    if not creds.client_id or not creds.client_secret:
        raise NotConnectedError(
            "Google Drive is not configured. Add a client ID and secret in Settings."
        )
    if not creds.refresh_token:
        raise NotConnectedError(
            "Google Drive is not connected. Authorise access in Settings."
        )

    cached = _token_cache.get(creds.refresh_token)
    if cached and cached[1] > time.time() + 60:
        logger.debug("Reusing cached Drive access token")
        return cached[0]

    logger.info("Refreshing Drive access token")
    payload = {
        "client_id": creds.client_id,
        "client_secret": creds.client_secret,
        "refresh_token": creds.refresh_token,
        "grant_type": "refresh_token",
    }
    async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT) as http:
        response = await http.post(TOKEN_ENDPOINT, data=payload)

    if response.status_code != 200:
        logger.error(
            "Drive token refresh failed: status=%s body=%s",
            response.status_code,
            response.text[:500],
        )
        _token_cache.pop(creds.refresh_token, None)
        raise NotConnectedError(_describe_token_error(response))

    tokens = response.json()
    access_token = tokens.get("access_token")
    if not access_token:
        raise NotConnectedError("Google returned no access token.")

    expires_in = int(tokens.get("expires_in", 3600))
    _token_cache[creds.refresh_token] = (access_token, time.time() + expires_in)
    logger.info("Drive access token refreshed (expires_in=%ds)", expires_in)
    return access_token


def forget_cached_token(refresh_token: str | None) -> None:
    """Drop a cached access token, e.g. on disconnect."""
    if refresh_token:
        _token_cache.pop(refresh_token, None)
        logger.debug("Cleared cached Drive access token")


def _describe_token_error(response: httpx.Response) -> str:
    """Turn a Google OAuth error body into something a user can act on."""
    try:
        body = response.json()
    except ValueError:
        return f"Google rejected the request (HTTP {response.status_code})."

    error = body.get("error", "")
    description = body.get("error_description", "")

    if error == "invalid_grant":
        return (
            "Google rejected the stored authorisation (invalid_grant). This "
            "usually means access was revoked or the token expired. Reconnect "
            "Google Drive in Settings."
        )
    if error == "invalid_client":
        return (
            "Google rejected the client ID or secret. Check both values in "
            "Settings against your Google Cloud credentials."
        )
    if error == "redirect_uri_mismatch":
        return (
            "The redirect URI does not match your Google Cloud OAuth client. "
            "Add the URI shown in Settings to the client's authorised redirect URIs."
        )
    return description or error or f"Google returned HTTP {response.status_code}."


async def get_account_email(creds: DriveCredentials) -> str | None:
    """Best-effort lookup of the connected Google account, for display."""
    try:
        token = await get_access_token(creds)
        async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT) as http:
            response = await http.get(
                USERINFO_ENDPOINT,
                headers={"Authorization": f"Bearer {token}"},
            )
        if response.status_code == 200:
            return response.json().get("email")
        logger.warning("Drive userinfo lookup returned HTTP %s", response.status_code)
    except GoogleDriveError:
        logger.warning("Drive userinfo lookup failed", exc_info=True)
    return None


# --------------------------------------------------------------------------
# Drive operations
# --------------------------------------------------------------------------


def _auth_headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _raise_for_api_error(response: httpx.Response, action: str) -> None:
    if response.status_code < 400:
        return
    logger.error(
        "Drive %s failed: status=%s body=%s",
        action,
        response.status_code,
        response.text[:500],
    )
    detail = ""
    try:
        detail = response.json().get("error", {}).get("message", "")
    except ValueError:
        pass
    if response.status_code in (401, 403):
        raise NotConnectedError(
            detail or "Google Drive rejected the request. Reconnect in Settings."
        )
    raise GoogleDriveError(detail or f"Drive {action} failed (HTTP {response.status_code}).")


async def ensure_folder(
    creds: DriveCredentials,
    name: str = DEFAULT_FOLDER_NAME,
    *,
    parent_id: str | None = None,
) -> str:
    """Return a folder id, creating the folder if it does not exist.

    With no ``parent_id`` this resolves the top-level Typecast folder and prefers
    the configured id. With one, it resolves a subfolder of that parent (used for
    the backups folder) and the configured id is not consulted.

    Under ``drive.file`` the search only ever sees folders this app created, so a
    folder the user made by hand will not be found and a new one is created.
    """
    if parent_id is None and creds.folder_id:
        logger.debug("Using configured Drive folder %s", creds.folder_id)
        return creds.folder_id

    token = await get_access_token(creds)
    clauses = [f"mimeType = '{FOLDER_MIME}'", f"name = '{name}'", "trashed = false"]
    if parent_id:
        clauses.append(f"'{parent_id}' in parents")
    query = " and ".join(clauses)

    async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT) as http:
        response = await http.get(
            FILES_ENDPOINT,
            headers=_auth_headers(token),
            params={"q": query, "fields": "files(id,name)", "pageSize": 10},
        )
        _raise_for_api_error(response, "folder lookup")
        files = response.json().get("files", [])
        if files:
            folder_id = files[0]["id"]
            logger.info("Found existing Drive folder %s (%s)", name, folder_id)
            return folder_id

        logger.info("Creating Drive folder %s", name)
        metadata: dict[str, object] = {"name": name, "mimeType": FOLDER_MIME}
        if parent_id:
            metadata["parents"] = [parent_id]
        response = await http.post(
            FILES_ENDPOINT,
            headers=_auth_headers(token),
            json=metadata,
            params={"fields": "id"},
        )
        _raise_for_api_error(response, "folder creation")
        folder_id = response.json()["id"]

    logger.info("Created Drive folder %s (%s)", name, folder_id)
    return folder_id


def split_folder_path(path: str) -> list[str]:
    """Split a user-typed folder path into clean segment names.

    Accepts either separator and tolerates leading, trailing, and repeated ones,
    so "/Drafts//2026/" is the same as "Drafts/2026". Segments of "." and ".."
    are dropped: there is no traversal to protect against in Drive (a parent is
    an id, not a path), but accepting them would silently create folders literally
    named "..".
    """
    segments = []
    for raw in path.replace("\\", "/").split("/"):
        name = raw.strip()
        if not name or name in {".", ".."}:
            continue
        segments.append(name[:MAX_NAME_LENGTH])
    return segments


async def ensure_folder_path(
    creds: DriveCredentials,
    path: str,
    *,
    root_id: str | None = None,
) -> str:
    """Resolve a nested folder path, creating any missing levels.

    Walks one level at a time from the Typecast folder (or ``root_id``). An empty
    path resolves to the root itself. Each level costs a lookup, which is why the
    path is expected to be short.
    """
    parent = root_id or await ensure_folder(creds)
    segments = split_folder_path(path)
    if not segments:
        return parent

    logger.info("Resolving Drive folder path %s under %s", "/".join(segments), parent)
    for segment in segments:
        parent = await ensure_folder(creds, segment, parent_id=parent)
    return parent


def sanitize_filename(name: str, *, extension: str | None = None) -> str:
    """Clean a user-supplied filename and apply the format's extension.

    Drive tolerates almost anything in a name, including slashes, but a slash
    reads as a path separator everywhere else and would make the file awkward to
    handle after download. ``extension`` is appended unless already present, so
    the format and the name cannot disagree.
    """
    cleaned = name.replace("\\", "-").replace("/", "-").strip().strip(".")
    cleaned = " ".join(cleaned.split())  # collapse whitespace runs
    # Require something substantive, so input like "///" or "..." is rejected
    # rather than becoming a file named "---".
    if not any(ch.isalnum() for ch in cleaned):
        raise ValueError("Filename has no usable characters")

    if extension:
        suffix = f".{extension.lstrip('.')}"
        if not cleaned.lower().endswith(suffix.lower()):
            cleaned = cleaned[: MAX_NAME_LENGTH - len(suffix)] + suffix
    return cleaned[:MAX_NAME_LENGTH]


async def upload_file(
    creds: DriveCredentials,
    *,
    content: bytes,
    filename: str,
    mime_type: str,
    folder_id: str | None = None,
    convert_to_google_doc: bool = False,
) -> DriveFile:
    """Upload bytes to Drive as a single multipart request.

    When ``convert_to_google_doc`` is set and the source type is convertible, the
    file lands as a native Google Doc — the point of the export integration, since
    a .docx sitting in Drive is not something a beta reader can comment on inline.
    """
    token = await get_access_token(creds)
    parent = folder_id or await ensure_folder(creds)

    metadata: dict[str, object] = {"name": filename, "parents": [parent]}
    target_mime = CONVERTIBLE_MIMES.get(mime_type) if convert_to_google_doc else None
    if target_mime:
        metadata["mimeType"] = target_mime

    logger.info(
        "Uploading %s to Drive (%d bytes, mime=%s, convert=%s, folder=%s)",
        filename,
        len(content),
        mime_type,
        bool(target_mime),
        parent,
    )

    # Drive's multipart upload wants the metadata part first, then the media.
    boundary = "typecast-gdrive-boundary"
    body = b"".join([
        f"--{boundary}\r\n".encode(),
        b"Content-Type: application/json; charset=UTF-8\r\n\r\n",
        json.dumps(metadata).encode(),
        f"\r\n--{boundary}\r\n".encode(),
        f"Content-Type: {mime_type}\r\n\r\n".encode(),
        content,
        f"\r\n--{boundary}--\r\n".encode(),
    ])

    async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT) as http:
        response = await http.post(
            UPLOAD_ENDPOINT,
            headers={
                **_auth_headers(token),
                "Content-Type": f"multipart/related; boundary={boundary}",
            },
            params={"uploadType": "multipart", "fields": "id,name,mimeType,webViewLink,size"},
            content=body,
        )
    _raise_for_api_error(response, "upload")

    result = DriveFile.from_api(response.json())
    logger.info("Uploaded %s to Drive as %s (%s)", filename, result.id, result.mime_type)
    return result


async def list_files(
    creds: DriveCredentials,
    *,
    folder_id: str | None = None,
    mime_type: str | None = None,
    name_contains: str | None = None,
    page_size: int = 100,
) -> list[DriveFile]:
    """List app-created files, newest first."""
    token = await get_access_token(creds)
    clauses = ["trashed = false"]
    if folder_id:
        clauses.append(f"'{folder_id}' in parents")
    if mime_type:
        clauses.append(f"mimeType = '{mime_type}'")
    if name_contains:
        escaped = name_contains.replace("'", "\\'")
        clauses.append(f"name contains '{escaped}'")

    async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT) as http:
        response = await http.get(
            FILES_ENDPOINT,
            headers=_auth_headers(token),
            params={
                "q": " and ".join(clauses),
                "fields": "files(id,name,mimeType,webViewLink,size,modifiedTime)",
                "orderBy": "modifiedTime desc",
                "pageSize": page_size,
            },
        )
    _raise_for_api_error(response, "list")

    files = [DriveFile.from_api(item) for item in response.json().get("files", [])]
    logger.info("Listed %d Drive file(s)", len(files))
    return files


async def download_file(creds: DriveCredentials, file_id: str) -> bytes:
    """Download a binary file this app created."""
    token = await get_access_token(creds)
    logger.info("Downloading Drive file %s", file_id)
    async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT) as http:
        response = await http.get(
            f"{FILES_ENDPOINT}/{file_id}",
            headers=_auth_headers(token),
            params={"alt": "media"},
            follow_redirects=True,
        )
    _raise_for_api_error(response, "download")
    logger.info("Downloaded %d bytes from Drive file %s", len(response.content), file_id)
    return response.content


async def delete_file(creds: DriveCredentials, file_id: str) -> None:
    """Permanently delete an app-created file."""
    token = await get_access_token(creds)
    logger.info("Deleting Drive file %s", file_id)
    async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT) as http:
        response = await http.delete(
            f"{FILES_ENDPOINT}/{file_id}",
            headers=_auth_headers(token),
        )
    if response.status_code == 404:
        logger.warning("Drive file %s already gone", file_id)
        return
    _raise_for_api_error(response, "delete")
    logger.info("Deleted Drive file %s", file_id)
