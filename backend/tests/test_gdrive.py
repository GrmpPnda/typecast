"""Google Drive integration tests.

Every Google HTTP call is mocked. What is under test is Typecast's own logic:
credential loading, the consent/callback state machine, token caching, multipart
body assembly, format-to-MIME mapping, and the conversion decision.
"""

from __future__ import annotations

import json
import time
import uuid

import httpx
import pytest

from app.api import gdrive as gdrive_api
from app.api.config import get_config_value, set_config_value
from app.services import gdrive


@pytest.fixture(autouse=True)
def clear_module_state():
    """Token cache and pending consent states are module-level; isolate tests."""
    gdrive._token_cache.clear()
    gdrive_api._pending_states.clear()
    yield
    gdrive._token_cache.clear()
    gdrive_api._pending_states.clear()


def _creds(**overrides) -> gdrive.DriveCredentials:
    base = {
        "client_id": "client-abc",
        "client_secret": "secret-xyz",
        "refresh_token": "refresh-123",
        "folder_id": None,
    }
    base.update(overrides)
    return gdrive.DriveCredentials(**base)


def _response(status: int, payload: dict | None = None, content: bytes | None = None):
    """Build an httpx.Response detached from any real transport."""
    request = httpx.Request("POST", "https://example.test")
    if content is not None:
        return httpx.Response(status, content=content, request=request)
    return httpx.Response(status, json=payload or {}, request=request)


class _FakeAsyncClient:
    """Stands in for httpx.AsyncClient, returning queued responses in order."""

    def __init__(self, responses):
        self._responses = list(responses)
        self.calls: list[tuple[str, str, dict]] = []

    def __call__(self, *args, **kwargs):
        return self

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def _record(self, method, url, **kwargs):
        self.calls.append((method, url, kwargs))
        if not self._responses:
            raise AssertionError(f"Unexpected {method} to {url}")
        return self._responses.pop(0)

    async def get(self, url, **kwargs):
        return await self._record("GET", url, **kwargs)

    async def post(self, url, **kwargs):
        return await self._record("POST", url, **kwargs)

    async def delete(self, url, **kwargs):
        return await self._record("DELETE", url, **kwargs)


# --------------------------------------------------------------------------
# Credentials and config
# --------------------------------------------------------------------------


async def test_credentials_default_to_unconfigured(db_session):
    creds = await gdrive.load_credentials(db_session)
    assert creds.client_id == ""
    assert creds.refresh_token is None
    assert creds.folder_id is None
    assert await gdrive.is_enabled(db_session) is False


async def test_client_secret_round_trips_encrypted(db_session):
    """Secrets are stored encrypted but read back in the clear."""
    await set_config_value(db_session, "gdrive_client_secret", "top-secret")

    creds = await gdrive.load_credentials(db_session)
    assert creds.client_secret == "top-secret"


async def test_secret_is_not_stored_in_plaintext(db_session):
    from sqlalchemy import select

    from app.models.config import AppConfig

    await set_config_value(db_session, "gdrive_refresh_token", "refresh-plain")

    result = await db_session.execute(
        select(AppConfig).where(AppConfig.key == "gdrive_refresh_token")
    )
    row = result.scalar_one()
    assert row.is_secret is True
    assert row.value != "refresh-plain"
    assert await get_config_value(db_session, "gdrive_refresh_token") == "refresh-plain"


async def test_set_config_value_rejects_unknown_key(db_session):
    with pytest.raises(ValueError):
        await set_config_value(db_session, "not_a_real_key", "x")


# --------------------------------------------------------------------------
# OAuth
# --------------------------------------------------------------------------


def test_auth_url_requests_offline_access_with_consent_prompt():
    """Without prompt=consent a repeat authorisation returns no refresh token."""
    url = gdrive.build_auth_url("cid", "http://localhost:8000/api/gdrive/callback", "state-1")

    assert url.startswith(gdrive.AUTH_ENDPOINT)
    assert "access_type=offline" in url
    assert "prompt=consent" in url
    assert "state=state-1" in url
    assert "drive.file" in url


def test_only_non_sensitive_drive_scope_is_requested():
    """drive.readonly or full drive are sensitive scopes and would force a Google
    verification review before the app could be published."""
    sensitive = {
        "https://www.googleapis.com/auth/drive",
        "https://www.googleapis.com/auth/drive.readonly",
        "https://www.googleapis.com/auth/drive.metadata.readonly",
    }
    assert sensitive.isdisjoint(gdrive.SCOPES)
    assert "https://www.googleapis.com/auth/drive.file" in gdrive.SCOPES


async def test_exchange_code_stores_refresh_token(monkeypatch):
    fake = _FakeAsyncClient([
        _response(200, {"access_token": "at", "refresh_token": "rt", "expires_in": 3600}),
    ])
    monkeypatch.setattr(gdrive.httpx, "AsyncClient", fake)

    tokens = await gdrive.exchange_code(
        code="code-1",
        client_id="cid",
        client_secret="cs",
        redirect_uri="http://localhost:8000/api/gdrive/callback",
    )
    assert tokens["refresh_token"] == "rt"


async def test_exchange_code_without_refresh_token_is_an_error(monkeypatch):
    """Google omits the refresh token on re-consent; silently storing nothing
    would look like success and fail later."""
    fake = _FakeAsyncClient([_response(200, {"access_token": "at", "expires_in": 3600})])
    monkeypatch.setattr(gdrive.httpx, "AsyncClient", fake)

    with pytest.raises(gdrive.GoogleDriveError, match="refresh token"):
        await gdrive.exchange_code(
            code="c", client_id="cid", client_secret="cs", redirect_uri="http://x/cb"
        )


async def test_invalid_grant_surfaces_actionable_message(monkeypatch):
    fake = _FakeAsyncClient([
        _response(400, {"error": "invalid_grant", "error_description": "Token revoked"}),
    ])
    monkeypatch.setattr(gdrive.httpx, "AsyncClient", fake)

    with pytest.raises(gdrive.NotConnectedError, match="Reconnect"):
        await gdrive.get_access_token(_creds())


async def test_redirect_uri_mismatch_names_the_fix(monkeypatch):
    fake = _FakeAsyncClient([_response(400, {"error": "redirect_uri_mismatch"})])
    monkeypatch.setattr(gdrive.httpx, "AsyncClient", fake)

    with pytest.raises(gdrive.NotConnectedError, match="redirect URI"):
        await gdrive.get_access_token(_creds())


async def test_access_token_requires_configuration():
    with pytest.raises(gdrive.NotConnectedError, match="not configured"):
        await gdrive.get_access_token(_creds(client_id="", client_secret=""))


async def test_access_token_requires_connection():
    with pytest.raises(gdrive.NotConnectedError, match="not connected"):
        await gdrive.get_access_token(_creds(refresh_token=None))


async def test_access_token_is_cached_between_calls(monkeypatch):
    fake = _FakeAsyncClient([
        _response(200, {"access_token": "at-1", "expires_in": 3600}),
    ])
    monkeypatch.setattr(gdrive.httpx, "AsyncClient", fake)

    creds = _creds()
    assert await gdrive.get_access_token(creds) == "at-1"
    # Second call must not hit the network; the queue holds only one response.
    assert await gdrive.get_access_token(creds) == "at-1"
    assert len(fake.calls) == 1


async def test_near_expiry_token_is_refreshed(monkeypatch):
    gdrive._token_cache["refresh-123"] = ("stale", time.time() + 10)
    fake = _FakeAsyncClient([_response(200, {"access_token": "fresh", "expires_in": 3600})])
    monkeypatch.setattr(gdrive.httpx, "AsyncClient", fake)

    assert await gdrive.get_access_token(_creds()) == "fresh"


async def test_failed_refresh_evicts_the_cached_token(monkeypatch):
    gdrive._token_cache["refresh-123"] = ("stale", time.time() + 10)
    fake = _FakeAsyncClient([_response(400, {"error": "invalid_grant"})])
    monkeypatch.setattr(gdrive.httpx, "AsyncClient", fake)

    with pytest.raises(gdrive.NotConnectedError):
        await gdrive.get_access_token(_creds())
    assert "refresh-123" not in gdrive._token_cache


def test_forget_cached_token_clears_the_entry():
    gdrive._token_cache["refresh-123"] = ("at", time.time() + 3600)
    gdrive.forget_cached_token("refresh-123")
    assert "refresh-123" not in gdrive._token_cache


# --------------------------------------------------------------------------
# Upload
# --------------------------------------------------------------------------


async def test_upload_builds_a_valid_multipart_body(monkeypatch):
    fake = _FakeAsyncClient([
        _response(200, {"access_token": "at", "expires_in": 3600}),
        _response(200, {
            "id": "file-1",
            "name": "Novel",
            "mimeType": gdrive.GOOGLE_DOC_MIME,
            "webViewLink": "https://docs.google.com/d/file-1",
        }),
    ])
    monkeypatch.setattr(gdrive.httpx, "AsyncClient", fake)

    result = await gdrive.upload_file(
        _creds(folder_id="folder-1"),
        content=b"BODYBYTES",
        filename="Novel",
        mime_type=(
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        ),
        folder_id="folder-1",
        convert_to_google_doc=True,
    )

    assert result.id == "file-1"
    assert result.mime_type == gdrive.GOOGLE_DOC_MIME

    _, url, kwargs = fake.calls[-1]
    assert url == gdrive.UPLOAD_ENDPOINT
    assert kwargs["params"]["uploadType"] == "multipart"
    body = kwargs["content"]
    assert b"BODYBYTES" in body

    # The metadata part must be parseable JSON naming the parent and target type.
    metadata_part = body.split(b"\r\n\r\n")[1].split(b"\r\n--")[0]
    metadata = json.loads(metadata_part)
    assert metadata["name"] == "Novel"
    assert metadata["parents"] == ["folder-1"]
    assert metadata["mimeType"] == gdrive.GOOGLE_DOC_MIME


async def test_upload_without_conversion_omits_target_mime(monkeypatch):
    fake = _FakeAsyncClient([
        _response(200, {"access_token": "at", "expires_in": 3600}),
        _response(200, {"id": "f", "name": "Novel.pdf", "mimeType": "application/pdf"}),
    ])
    monkeypatch.setattr(gdrive.httpx, "AsyncClient", fake)

    await gdrive.upload_file(
        _creds(folder_id="folder-1"),
        content=b"%PDF-1.7",
        filename="Novel.pdf",
        mime_type="application/pdf",
        folder_id="folder-1",
        convert_to_google_doc=False,
    )

    body = fake.calls[-1][2]["content"]
    metadata = json.loads(body.split(b"\r\n\r\n")[1].split(b"\r\n--")[0])
    assert "mimeType" not in metadata


async def test_pdf_is_not_convertible():
    """Only editor-compatible formats convert; PDF must upload as a PDF."""
    assert "application/pdf" not in gdrive.CONVERTIBLE_MIMES
    assert "application/epub+zip" not in gdrive.CONVERTIBLE_MIMES
    docx = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    assert gdrive.CONVERTIBLE_MIMES[docx] == gdrive.GOOGLE_DOC_MIME


async def test_upload_rejection_raises_not_connected(monkeypatch):
    """A 403 from Drive means re-auth, not a transient failure."""
    fake = _FakeAsyncClient([
        _response(200, {"access_token": "at", "expires_in": 3600}),
        _response(403, {"error": {"message": "Insufficient permission"}}),
    ])
    monkeypatch.setattr(gdrive.httpx, "AsyncClient", fake)

    with pytest.raises(gdrive.NotConnectedError, match="Insufficient permission"):
        await gdrive.upload_file(
            _creds(folder_id="f"),
            content=b"x",
            filename="x.pdf",
            mime_type="application/pdf",
            folder_id="f",
        )


# --------------------------------------------------------------------------
# Folder handling
# --------------------------------------------------------------------------


async def test_configured_folder_skips_lookup(monkeypatch):
    fake = _FakeAsyncClient([])  # any call would raise
    monkeypatch.setattr(gdrive.httpx, "AsyncClient", fake)

    assert await gdrive.ensure_folder(_creds(folder_id="existing")) == "existing"
    assert fake.calls == []


async def test_existing_folder_is_reused(monkeypatch):
    fake = _FakeAsyncClient([
        _response(200, {"access_token": "at", "expires_in": 3600}),
        _response(200, {"files": [{"id": "found-1", "name": "Typecast"}]}),
    ])
    monkeypatch.setattr(gdrive.httpx, "AsyncClient", fake)

    assert await gdrive.ensure_folder(_creds()) == "found-1"


async def test_missing_folder_is_created(monkeypatch):
    fake = _FakeAsyncClient([
        _response(200, {"access_token": "at", "expires_in": 3600}),
        _response(200, {"files": []}),
        _response(200, {"id": "new-1"}),
    ])
    monkeypatch.setattr(gdrive.httpx, "AsyncClient", fake)

    assert await gdrive.ensure_folder(_creds()) == "new-1"
    method, url, kwargs = fake.calls[-1]
    assert method == "POST"
    assert kwargs["json"]["mimeType"] == gdrive.FOLDER_MIME


# --------------------------------------------------------------------------
# Endpoints
# --------------------------------------------------------------------------


async def test_status_reports_unconfigured(client):
    response = await client.get("/api/gdrive/status")
    assert response.status_code == 200
    body = response.json()
    assert body["configured"] is False
    assert body["connected"] is False
    assert body["redirect_uri"].endswith("/api/gdrive/callback")


async def test_auth_url_requires_client_credentials(client):
    response = await client.get("/api/gdrive/auth-url")
    assert response.status_code == 400
    assert "client ID" in response.json()["detail"]


async def test_auth_url_returned_once_configured(client, db_session):
    await set_config_value(db_session, "gdrive_client_id", "cid")
    await set_config_value(db_session, "gdrive_client_secret", "cs")

    response = await client.get("/api/gdrive/auth-url")
    assert response.status_code == 200
    assert response.json()["auth_url"].startswith(gdrive.AUTH_ENDPOINT)
    assert len(gdrive_api._pending_states) == 1


async def test_callback_rejects_unknown_state(client):
    """Guards against a forged callback completing the connection."""
    response = await client.get("/api/gdrive/callback", params={"code": "c", "state": "forged"})
    assert response.status_code == 200
    assert "not recognised" in response.text


async def test_callback_reports_denied_consent(client):
    response = await client.get("/api/gdrive/callback", params={"error": "access_denied"})
    assert "access_denied" in response.text
    assert "Connection failed" in response.text


async def test_callback_stores_token_and_enables(client, db_session, monkeypatch):
    await set_config_value(db_session, "gdrive_client_id", "cid")
    await set_config_value(db_session, "gdrive_client_secret", "cs")

    fake = _FakeAsyncClient([
        _response(200, {"access_token": "at", "refresh_token": "rt-new", "expires_in": 3600}),
    ])
    monkeypatch.setattr(gdrive.httpx, "AsyncClient", fake)

    auth = await client.get("/api/gdrive/auth-url")
    state = next(iter(gdrive_api._pending_states))
    assert auth.status_code == 200

    response = await client.get("/api/gdrive/callback", params={"code": "c", "state": state})
    assert response.status_code == 200
    assert "Connected" in response.text

    assert await get_config_value(db_session, "gdrive_refresh_token") == "rt-new"
    assert await get_config_value(db_session, "gdrive_enabled") == "true"


async def test_callback_state_is_single_use(client, db_session, monkeypatch):
    await set_config_value(db_session, "gdrive_client_id", "cid")
    await set_config_value(db_session, "gdrive_client_secret", "cs")
    fake = _FakeAsyncClient([
        _response(200, {"access_token": "at", "refresh_token": "rt", "expires_in": 3600}),
    ])
    monkeypatch.setattr(gdrive.httpx, "AsyncClient", fake)

    await client.get("/api/gdrive/auth-url")
    state = next(iter(gdrive_api._pending_states))

    first = await client.get("/api/gdrive/callback", params={"code": "c", "state": state})
    assert "Connected" in first.text

    replay = await client.get("/api/gdrive/callback", params={"code": "c", "state": state})
    assert "not recognised" in replay.text


async def test_disconnect_clears_the_token(client, db_session):
    await set_config_value(db_session, "gdrive_client_id", "cid")
    await set_config_value(db_session, "gdrive_client_secret", "cs")
    await set_config_value(db_session, "gdrive_refresh_token", "rt")
    await set_config_value(db_session, "gdrive_enabled", "true")

    response = await client.post("/api/gdrive/disconnect")
    assert response.status_code == 200
    assert response.json()["connected"] is False

    assert await get_config_value(db_session, "gdrive_refresh_token") == ""
    assert await get_config_value(db_session, "gdrive_enabled") == "false"


async def _owned_work(client) -> str:
    """A real work owned by the test account; a random ID is now a 404."""
    resp = await client.post("/api/works/", json={"title": "Drive Test", "author": "A"})
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


async def test_export_requires_connection(client):
    work_id = await _owned_work(client)
    response = await client.post(
        f"/api/gdrive/works/{work_id}/export",
        json={"format": "docx"},
    )
    assert response.status_code == 400
    assert "not connected" in response.json()["detail"]


async def test_export_missing_work_is_404(client, db_session, monkeypatch):
    await set_config_value(db_session, "gdrive_client_id", "cid")
    await set_config_value(db_session, "gdrive_client_secret", "cs")
    await set_config_value(db_session, "gdrive_refresh_token", "rt")

    response = await client.post(
        f"/api/gdrive/works/{uuid.uuid4()}/export",
        json={"format": "docx"},
    )
    assert response.status_code == 404


async def test_export_uploads_and_returns_link(client, db_session, monkeypatch):
    """End-to-end through the endpoint: render a real work, mock only Google."""
    await set_config_value(db_session, "gdrive_client_id", "cid")
    await set_config_value(db_session, "gdrive_client_secret", "cs")
    await set_config_value(db_session, "gdrive_refresh_token", "rt")

    work = await client.post("/api/works/", json={"title": "Drive Novel", "author": "Tester"})
    assert work.status_code == 201
    work_id = work.json()["id"]

    fake = _FakeAsyncClient([
        _response(200, {"access_token": "at", "expires_in": 3600}),
        _response(200, {"files": [{"id": "folder-1", "name": "Typecast"}]}),
        _response(200, {
            "id": "doc-1",
            "name": "Drive Novel",
            "mimeType": gdrive.GOOGLE_DOC_MIME,
            "webViewLink": "https://docs.google.com/document/d/doc-1",
        }),
    ])
    monkeypatch.setattr(gdrive.httpx, "AsyncClient", fake)

    response = await client.post(
        f"/api/gdrive/works/{work_id}/export",
        json={"format": "markdown", "convert_to_google_doc": True},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["file_id"] == "doc-1"
    assert body["converted_to_google_doc"] is True
    assert body["web_view_link"].startswith("https://docs.google.com/")

    # The discovered folder should be remembered for later uploads.
    assert await get_config_value(db_session, "gdrive_folder_id") == "folder-1"


async def test_export_strips_extension_when_converting(client, db_session, monkeypatch):
    """A converted file becomes a Google Doc, so a .md suffix would mislead."""
    await set_config_value(db_session, "gdrive_client_id", "cid")
    await set_config_value(db_session, "gdrive_client_secret", "cs")
    await set_config_value(db_session, "gdrive_refresh_token", "rt")
    await set_config_value(db_session, "gdrive_folder_id", "folder-1")

    work = await client.post("/api/works/", json={"title": "Suffix Test", "author": "T"})
    work_id = work.json()["id"]

    fake = _FakeAsyncClient([
        _response(200, {"access_token": "at", "expires_in": 3600}),
        _response(200, {"id": "d", "name": "Suffix Test", "mimeType": gdrive.GOOGLE_DOC_MIME}),
    ])
    monkeypatch.setattr(gdrive.httpx, "AsyncClient", fake)

    await client.post(
        f"/api/gdrive/works/{work_id}/export",
        json={"format": "markdown", "convert_to_google_doc": True},
    )

    body = fake.calls[-1][2]["content"]
    metadata = json.loads(body.split(b"\r\n\r\n")[1].split(b"\r\n--")[0])
    assert not metadata["name"].endswith(".md")


async def test_export_keeps_extension_for_pdf(client, db_session, monkeypatch):
    """PDF cannot convert, so the filename must keep its suffix even when the
    caller asks for conversion."""
    await set_config_value(db_session, "gdrive_client_id", "cid")
    await set_config_value(db_session, "gdrive_client_secret", "cs")
    await set_config_value(db_session, "gdrive_refresh_token", "rt")
    await set_config_value(db_session, "gdrive_folder_id", "folder-1")

    work = await client.post("/api/works/", json={"title": "Pdf Test", "author": "T"})
    work_id = work.json()["id"]

    fake = _FakeAsyncClient([
        _response(200, {"access_token": "at", "expires_in": 3600}),
        _response(200, {"id": "p", "name": "Pdf Test.pdf", "mimeType": "application/pdf"}),
    ])
    monkeypatch.setattr(gdrive.httpx, "AsyncClient", fake)

    response = await client.post(
        f"/api/gdrive/works/{work_id}/export",
        json={"format": "pdf", "convert_to_google_doc": True},
    )
    assert response.status_code == 200
    assert response.json()["converted_to_google_doc"] is False

    body = fake.calls[-1][2]["content"]
    metadata = json.loads(body.split(b"\r\n\r\n")[1].split(b"\r\n--")[0])
    assert metadata["name"].endswith(".pdf")
    assert "mimeType" not in metadata


async def test_export_rejects_unknown_format(client):
    work_id = await _owned_work(client)
    response = await client.post(
        f"/api/gdrive/works/{work_id}/export",
        json={"format": "mobi"},
    )
    assert response.status_code == 422


async def test_every_export_format_has_a_mime_type():
    """Guards the format list against drifting from app/api/export.py."""
    from app.api.export import ExportFormat

    for fmt in ExportFormat:
        assert fmt.value in gdrive_api._EXPORT_MIME


# --------------------------------------------------------------------------
# Export destination: folder path and filename
# --------------------------------------------------------------------------


def test_folder_path_splitting_tolerates_untidy_input():
    assert gdrive.split_folder_path("Drafts/2026") == ["Drafts", "2026"]
    assert gdrive.split_folder_path("/Drafts//2026/") == ["Drafts", "2026"]
    assert gdrive.split_folder_path("Drafts\\2026") == ["Drafts", "2026"]
    assert gdrive.split_folder_path("  Drafts / 2026  ") == ["Drafts", "2026"]
    assert gdrive.split_folder_path("") == []
    assert gdrive.split_folder_path("   ") == []


def test_folder_path_drops_dot_segments():
    """Not a traversal risk in Drive, but folders named ".." would be nonsense."""
    assert gdrive.split_folder_path("../../etc") == ["etc"]
    assert gdrive.split_folder_path("./Drafts") == ["Drafts"]
    assert gdrive.split_folder_path("../..") == []


def test_filename_sanitising_strips_separators():
    """A slash reads as a path separator once the file is downloaded."""
    assert gdrive.sanitize_filename("My/Novel") == "My-Novel"
    assert gdrive.sanitize_filename("My\\Novel") == "My-Novel"
    assert gdrive.sanitize_filename("  spaced   out  ") == "spaced out"


def test_filename_extension_is_applied_once():
    assert gdrive.sanitize_filename("Draft", extension="pdf") == "Draft.pdf"
    assert gdrive.sanitize_filename("Draft.pdf", extension="pdf") == "Draft.pdf"
    assert gdrive.sanitize_filename("Draft.PDF", extension="pdf") == "Draft.PDF"
    assert gdrive.sanitize_filename("Draft.docx", extension="pdf") == "Draft.docx.pdf"


def test_filename_length_is_capped():
    result = gdrive.sanitize_filename("x" * 400, extension="pdf")
    assert len(result) <= gdrive.MAX_NAME_LENGTH
    assert result.endswith(".pdf")


def test_empty_filename_is_rejected():
    for bad in ["", "   ", "...", "///"]:
        with pytest.raises(ValueError):
            gdrive.sanitize_filename(bad, extension="pdf")


async def test_folder_path_walks_one_level_at_a_time(monkeypatch):
    fake = _FakeAsyncClient([
        _response(200, {"access_token": "at", "expires_in": 3600}),
        _response(200, {"files": [{"id": "drafts-1", "name": "Drafts"}]}),
        _response(200, {"files": []}),
        _response(200, {"id": "2026-1"}),
    ])
    monkeypatch.setattr(gdrive.httpx, "AsyncClient", fake)

    folder_id = await gdrive.ensure_folder_path(
        _creds(folder_id="root-1"), "Drafts/2026", root_id="root-1"
    )

    assert folder_id == "2026-1"
    # The second level must be created inside the first, not beside it.
    assert fake.calls[-1][2]["json"]["parents"] == ["drafts-1"]


async def test_empty_folder_path_resolves_to_the_root():
    """No path means the Typecast folder itself, with no extra API calls."""
    folder_id = await gdrive.ensure_folder_path(
        _creds(folder_id="root-1"), "", root_id="root-1"
    )
    assert folder_id == "root-1"


async def test_export_uploads_into_the_requested_folder(client, db_session, monkeypatch):
    await set_config_value(db_session, "gdrive_client_id", "cid")
    await set_config_value(db_session, "gdrive_client_secret", "cs")
    await set_config_value(db_session, "gdrive_refresh_token", "rt")
    await set_config_value(db_session, "gdrive_folder_id", "folder-1")

    work = await client.post("/api/works/", json={"title": "Path Test", "author": "T"})
    work_id = work.json()["id"]

    fake = _FakeAsyncClient([
        _response(200, {"access_token": "at", "expires_in": 3600}),
        _response(200, {"files": [{"id": "beta-1", "name": "Beta"}]}),
        _response(200, {"id": "p", "name": "Path Test.pdf", "mimeType": "application/pdf"}),
    ])
    monkeypatch.setattr(gdrive.httpx, "AsyncClient", fake)

    response = await client.post(
        f"/api/gdrive/works/{work_id}/export",
        json={"format": "pdf", "folder_path": "Beta"},
    )
    assert response.status_code == 200, response.text
    assert response.json()["folder_path"] == "Beta"

    metadata = json.loads(fake.calls[-1][2]["content"].split(b"\r\n\r\n")[1].split(b"\r\n--")[0])
    assert metadata["parents"] == ["beta-1"]


async def test_export_uses_the_requested_filename(client, db_session, monkeypatch):
    await set_config_value(db_session, "gdrive_client_id", "cid")
    await set_config_value(db_session, "gdrive_client_secret", "cs")
    await set_config_value(db_session, "gdrive_refresh_token", "rt")
    await set_config_value(db_session, "gdrive_folder_id", "folder-1")

    work = await client.post("/api/works/", json={"title": "Ignored Title", "author": "T"})
    work_id = work.json()["id"]

    fake = _FakeAsyncClient([
        _response(200, {"access_token": "at", "expires_in": 3600}),
        _response(200, {"id": "p", "name": "x", "mimeType": "application/pdf"}),
    ])
    monkeypatch.setattr(gdrive.httpx, "AsyncClient", fake)

    response = await client.post(
        f"/api/gdrive/works/{work_id}/export",
        json={"format": "pdf", "filename": "Reader Copy v3"},
    )
    assert response.status_code == 200, response.text

    metadata = json.loads(fake.calls[-1][2]["content"].split(b"\r\n\r\n")[1].split(b"\r\n--")[0])
    # The extension comes from the format, not the user, so they cannot disagree.
    assert metadata["name"] == "Reader Copy v3.pdf"


async def test_custom_filename_loses_its_extension_when_converting(
    client, db_session, monkeypatch
):
    await set_config_value(db_session, "gdrive_client_id", "cid")
    await set_config_value(db_session, "gdrive_client_secret", "cs")
    await set_config_value(db_session, "gdrive_refresh_token", "rt")
    await set_config_value(db_session, "gdrive_folder_id", "folder-1")

    work = await client.post("/api/works/", json={"title": "Conv", "author": "T"})
    work_id = work.json()["id"]

    fake = _FakeAsyncClient([
        _response(200, {"access_token": "at", "expires_in": 3600}),
        _response(200, {"id": "d", "name": "x", "mimeType": gdrive.GOOGLE_DOC_MIME}),
    ])
    monkeypatch.setattr(gdrive.httpx, "AsyncClient", fake)

    await client.post(
        f"/api/gdrive/works/{work_id}/export",
        json={"format": "docx", "filename": "Reader Copy", "convert_to_google_doc": True},
    )

    metadata = json.loads(fake.calls[-1][2]["content"].split(b"\r\n\r\n")[1].split(b"\r\n--")[0])
    assert metadata["name"] == "Reader Copy"


async def test_export_rejects_a_filename_that_cleans_to_nothing(client, db_session):
    await set_config_value(db_session, "gdrive_client_id", "cid")
    await set_config_value(db_session, "gdrive_client_secret", "cs")
    await set_config_value(db_session, "gdrive_refresh_token", "rt")

    work = await client.post("/api/works/", json={"title": "Bad Name", "author": "T"})
    work_id = work.json()["id"]

    response = await client.post(
        f"/api/gdrive/works/{work_id}/export",
        json={"format": "pdf", "filename": "///"},
    )
    assert response.status_code == 400
    assert "Filename" in response.json()["detail"]


async def test_export_without_a_destination_keeps_the_old_behaviour(
    client, db_session, monkeypatch
):
    """Defaults must not change: root folder, title-derived filename."""
    await set_config_value(db_session, "gdrive_client_id", "cid")
    await set_config_value(db_session, "gdrive_client_secret", "cs")
    await set_config_value(db_session, "gdrive_refresh_token", "rt")
    await set_config_value(db_session, "gdrive_folder_id", "folder-1")

    work = await client.post("/api/works/", json={"title": "Default Dest", "author": "T"})
    work_id = work.json()["id"]

    fake = _FakeAsyncClient([
        _response(200, {"access_token": "at", "expires_in": 3600}),
        _response(200, {"id": "p", "name": "x", "mimeType": "application/pdf"}),
    ])
    monkeypatch.setattr(gdrive.httpx, "AsyncClient", fake)

    response = await client.post(
        f"/api/gdrive/works/{work_id}/export", json={"format": "pdf"}
    )
    assert response.status_code == 200
    assert response.json()["folder_path"] == ""

    metadata = json.loads(fake.calls[-1][2]["content"].split(b"\r\n\r\n")[1].split(b"\r\n--")[0])
    assert metadata["parents"] == ["folder-1"]
    # _safe_filename in the export service underscores spaces; unchanged by this feature.
    assert metadata["name"] == "Default_Dest.pdf"


async def test_files_listing_requires_connection(client):
    response = await client.get("/api/gdrive/files")
    assert response.status_code == 400


async def test_files_listing_returns_drive_files(client, db_session, monkeypatch):
    await set_config_value(db_session, "gdrive_client_id", "cid")
    await set_config_value(db_session, "gdrive_client_secret", "cs")
    await set_config_value(db_session, "gdrive_refresh_token", "rt")
    await set_config_value(db_session, "gdrive_folder_id", "folder-1")

    fake = _FakeAsyncClient([
        _response(200, {"access_token": "at", "expires_in": 3600}),
        _response(200, {"files": [
            {
                "id": "f1",
                "name": "Novel",
                "mimeType": gdrive.GOOGLE_DOC_MIME,
                "webViewLink": "https://docs.google.com/d/f1",
                "modifiedTime": "2026-08-01T10:00:00Z",
            },
        ]}),
    ])
    monkeypatch.setattr(gdrive.httpx, "AsyncClient", fake)

    response = await client.get("/api/gdrive/files")
    assert response.status_code == 200
    files = response.json()
    assert len(files) == 1
    assert files[0]["id"] == "f1"
    assert files[0]["size"] is None
