"""Backup-to-Drive tests.

Two layers. The archive service is exercised against a temporary data directory
so a real ZIP is built and restored without touching the dev database. The Drive
endpoints are exercised with every Google HTTP call mocked, and with the archive
functions stubbed so an endpoint test can never write to the filesystem.
"""

from __future__ import annotations

import io
import json
import zipfile

import pytest

from app.api import gdrive as gdrive_api
from app.api.config import set_config_value
from app.services import backup as backup_service
from app.services import gdrive
from tests.test_gdrive import _FakeAsyncClient, _response


@pytest.fixture(autouse=True)
def clear_token_cache():
    gdrive._token_cache.clear()
    yield
    gdrive._token_cache.clear()


@pytest.fixture
def data_dir(tmp_path, monkeypatch, engine):
    """Point the archive service at a scratch directory and the test engine.

    Without this the service would read and overwrite backend/typecast.db.
    """
    db_path = tmp_path / "typecast.db"
    db_path.write_bytes(b"SQLite format 3\x00fake-database")
    uploads = tmp_path / "uploads"
    (uploads / "images" / "work-1").mkdir(parents=True)
    (uploads / "images" / "work-1" / "cover.png").write_bytes(b"png-bytes")
    (uploads / "fonts").mkdir()
    (uploads / "fonts" / "serif.ttf").write_bytes(b"ttf-bytes")

    monkeypatch.setattr(backup_service, "DATA_DIR", tmp_path)
    monkeypatch.setattr(backup_service, "DB_PATH", db_path)
    monkeypatch.setattr(backup_service, "UPLOAD_DIR", uploads)
    monkeypatch.setattr(backup_service, "engine", engine)
    return tmp_path


async def _connect(db_session, folder_id: str | None = "folder-1"):
    await set_config_value(db_session, "gdrive_client_id", "cid")
    await set_config_value(db_session, "gdrive_client_secret", "cs")
    await set_config_value(db_session, "gdrive_refresh_token", "rt")
    if folder_id:
        await set_config_value(db_session, "gdrive_folder_id", folder_id)


def _token():
    return _response(200, {"access_token": "at", "expires_in": 3600})


def _backup_folder_lookup(folder_id: str = "backups-1"):
    """The single list response that resolves the Backups subfolder."""
    return _response(200, {"files": [{"id": folder_id, "name": "Backups"}]})


def _backup_list(names: list[str]):
    return _response(200, {
        "files": [
            {"id": f"id-{n}", "name": n, "mimeType": backup_service.BACKUP_MIME, "size": "10"}
            for n in names
        ]
    })


def _stub_archive(monkeypatch, *, filename="typecast-backup-20260805-120000.zip"):
    """Replace archive building so endpoint tests never touch the filesystem."""
    async def fake_build():
        return b"zip-bytes", filename

    monkeypatch.setattr(gdrive_api, "build_backup_archive", fake_build)


# --------------------------------------------------------------------------
# Archive service
# --------------------------------------------------------------------------


def _legacy_archive(**entries) -> bytes:
    """A version 1 archive: a SQLite file plus uploads. Existing Drive backups."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("typecast.db", entries.pop("db", b"SQLite format 3\x00archived-database"))
        for name, data in entries.items():
            zf.writestr(name.replace("__", "/"), data)
    return buf.getvalue()


def test_data_dir_honours_the_env_var(tmp_path):
    """TYPECAST_DATA_DIR must drive the paths, not the backend directory."""
    elsewhere = tmp_path / "elsewhere"
    assert backup_service.resolve_data_dir({"TYPECAST_DATA_DIR": str(elsewhere)}) == elsewhere


def test_data_dir_falls_back_to_the_backend_directory():
    assert backup_service.resolve_data_dir({}) == backup_service.BACKEND_DIR


async def test_legacy_archive_still_restores_on_sqlite(data_dir):
    """Archives made before format version 2 must stay restorable here.

    The archive-format tests themselves live in test_archive.py.
    """
    (data_dir / "uploads" / "stale.txt").write_bytes(b"should-not-survive")
    content = _legacy_archive(uploads__images__work_1__cover_png=b"png-bytes")

    summary = await backup_service.restore_backup_archive(content)

    assert summary.files_written == 1
    assert (data_dir / "typecast.db").read_bytes() == b"SQLite format 3\x00archived-database"
    assert not (data_dir / "uploads" / "stale.txt").exists()


async def test_restore_rejects_a_zip_that_is_not_a_typecast_archive(data_dir):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("uploads/thing.txt", "x")

    with pytest.raises(backup_service.BackupError, match="not a Typecast archive"):
        await backup_service.restore_backup_archive(buf.getvalue())

    # The existing database must be untouched by a rejected archive.
    assert (data_dir / "typecast.db").read_bytes() == b"SQLite format 3\x00fake-database"


async def test_restore_rejects_a_non_zip(data_dir):
    with pytest.raises(backup_service.BackupError, match="ZIP"):
        await backup_service.restore_backup_archive(b"not a zip at all")


async def test_legacy_restore_skips_path_traversal_entries(data_dir):
    """A hand-edited archive must not write outside the uploads directory."""
    content = _legacy_archive(**{"uploads/../../escaped.txt": b"pwned"})

    summary = await backup_service.restore_backup_archive(content)

    assert summary.files_written == 0
    assert not (data_dir.parent / "escaped.txt").exists()


def test_only_typecast_archives_are_recognised():
    """Retention deletes files, so the name filter gates what is eligible."""
    assert backup_service.is_backup_filename("typecast-backup-20260805-120000.zip")
    assert not backup_service.is_backup_filename("my-novel.zip")
    assert not backup_service.is_backup_filename("typecast-backup-notes.txt")
    assert not backup_service.is_backup_filename("Chapter One.docx")


def test_archive_names_sort_newest_first_lexically():
    """Retention orders by name, so the timestamp format must sort correctly."""
    names = [
        "typecast-backup-20260805-090000.zip",
        "typecast-backup-20251231-235959.zip",
        "typecast-backup-20260805-120000.zip",
    ]
    assert sorted(names, reverse=True)[0] == "typecast-backup-20260805-120000.zip"
    assert sorted(names, reverse=True)[-1] == "typecast-backup-20251231-235959.zip"


# --------------------------------------------------------------------------
# Backups folder
# --------------------------------------------------------------------------


async def test_backup_folder_is_a_subfolder_of_the_typecast_folder(monkeypatch):
    fake = _FakeAsyncClient([_token(), _backup_folder_lookup()])
    monkeypatch.setattr(gdrive.httpx, "AsyncClient", fake)

    folder_id = await gdrive_api._backup_folder(_creds_with_folder())

    assert folder_id == "backups-1"
    _, _, kwargs = fake.calls[-1]
    assert "'folder-1' in parents" in kwargs["params"]["q"]
    assert "name = 'Backups'" in kwargs["params"]["q"]


async def test_backup_folder_is_created_when_absent(monkeypatch):
    fake = _FakeAsyncClient([
        _token(),
        _response(200, {"files": []}),
        _response(200, {"id": "backups-new"}),
    ])
    monkeypatch.setattr(gdrive.httpx, "AsyncClient", fake)

    folder_id = await gdrive_api._backup_folder(_creds_with_folder())

    assert folder_id == "backups-new"
    _, _, kwargs = fake.calls[-1]
    assert kwargs["json"]["parents"] == ["folder-1"]
    assert kwargs["json"]["mimeType"] == gdrive.FOLDER_MIME


def _creds_with_folder():
    return gdrive.DriveCredentials(
        client_id="cid",
        client_secret="cs",
        refresh_token="rt",
        folder_id="folder-1",
    )


# --------------------------------------------------------------------------
# Backup endpoint
# --------------------------------------------------------------------------


async def test_backup_requires_connection(client):
    response = await client.post("/api/gdrive/backup", json={})
    assert response.status_code == 400
    assert "not connected" in response.json()["detail"]


async def test_backup_uploads_the_archive(client, db_session, monkeypatch):
    await _connect(db_session)
    _stub_archive(monkeypatch)

    fake = _FakeAsyncClient([
        _token(),
        _backup_folder_lookup(),
        _response(200, {
            "id": "drive-1",
            "name": "typecast-backup-20260805-120000.zip",
            "mimeType": backup_service.BACKUP_MIME,
            "webViewLink": "https://drive.google.com/f/drive-1",
        }),
    ])
    monkeypatch.setattr(gdrive.httpx, "AsyncClient", fake)

    response = await client.post("/api/gdrive/backup", json={})
    assert response.status_code == 200
    body = response.json()
    assert body["file_id"] == "drive-1"
    assert body["size"] == len(b"zip-bytes")
    assert body["pruned"] == []


async def test_backup_uploads_into_the_backups_folder_as_zip(client, db_session, monkeypatch):
    await _connect(db_session)
    _stub_archive(monkeypatch)

    fake = _FakeAsyncClient([
        _token(),
        _backup_folder_lookup(),
        _response(200, {"id": "drive-1", "name": "b.zip", "mimeType": backup_service.BACKUP_MIME}),
    ])
    monkeypatch.setattr(gdrive.httpx, "AsyncClient", fake)

    await client.post("/api/gdrive/backup", json={})

    _, url, kwargs = fake.calls[-1]
    assert url == gdrive.UPLOAD_ENDPOINT
    metadata = json.loads(kwargs["content"].split(b"\r\n\r\n")[1].split(b"\r\n--")[0])
    assert metadata["parents"] == ["backups-1"]
    # An archive must never be converted to a Google Doc.
    assert "mimeType" not in metadata
    assert backup_service.BACKUP_MIME.encode() in kwargs["content"]


async def test_backup_without_keep_prunes_nothing(client, db_session, monkeypatch):
    """Retention is opt-in: deleting a user's archives must be requested."""
    await _connect(db_session)
    _stub_archive(monkeypatch)

    fake = _FakeAsyncClient([
        _token(),
        _backup_folder_lookup(),
        _response(200, {"id": "drive-1", "name": "b.zip", "mimeType": backup_service.BACKUP_MIME}),
    ])
    monkeypatch.setattr(gdrive.httpx, "AsyncClient", fake)

    response = await client.post("/api/gdrive/backup", json={})
    assert response.status_code == 200
    assert response.json()["pruned"] == []
    # No list-for-retention and no delete calls were made.
    assert not [c for c in fake.calls if c[0] == "DELETE"]


async def test_backup_prunes_beyond_the_keep_count(client, db_session, monkeypatch):
    await _connect(db_session)
    _stub_archive(monkeypatch)

    names = [
        "typecast-backup-20260805-120000.zip",  # the new one
        "typecast-backup-20260804-120000.zip",
        "typecast-backup-20260803-120000.zip",
        "typecast-backup-20260802-120000.zip",
    ]
    fake = _FakeAsyncClient([
        _token(),
        _backup_folder_lookup(),
        _response(200, {"id": "id-" + names[0], "name": names[0],
                        "mimeType": backup_service.BACKUP_MIME}),
        _backup_folder_lookup(),  # retention re-resolves the folder
        _backup_list(names),
        _response(204),  # delete 20260803
        _response(204),  # delete 20260802
    ])
    monkeypatch.setattr(gdrive.httpx, "AsyncClient", fake)

    response = await client.post("/api/gdrive/backup", json={"keep": 2})
    assert response.status_code == 200
    assert response.json()["pruned"] == [names[2], names[3]]

    deleted = [c[1] for c in fake.calls if c[0] == "DELETE"]
    assert len(deleted) == 2
    assert deleted[0].endswith(f"id-{names[2]}")


async def test_pruning_never_deletes_the_archive_just_uploaded(monkeypatch):
    """A clock skew must not let retention delete the backup it just made."""
    names = ["typecast-backup-20260805-120000.zip", "typecast-backup-20260101-000000.zip"]
    fake = _FakeAsyncClient([
        _token(),
        _backup_folder_lookup(),
        _backup_list(names),
        _response(204),  # only the older archive may be deleted
    ])
    monkeypatch.setattr(gdrive.httpx, "AsyncClient", fake)

    # keep=0 would normally make everything stale.
    pruned = await gdrive_api._prune_backups(
        _creds_with_folder(), keep=0, protect_id=f"id-{names[0]}"
    )

    assert pruned == [names[1]]


async def test_pruning_failure_does_not_fail_the_backup(client, db_session, monkeypatch):
    """The upload already succeeded; a prune error must not read as a failure."""
    await _connect(db_session)
    _stub_archive(monkeypatch)

    fake = _FakeAsyncClient([
        _token(),
        _backup_folder_lookup(),
        _response(200, {"id": "drive-1", "name": "b.zip", "mimeType": backup_service.BACKUP_MIME}),
        _backup_folder_lookup(),
        _response(500, {"error": {"message": "listing blew up"}}),
    ])
    monkeypatch.setattr(gdrive.httpx, "AsyncClient", fake)

    response = await client.post("/api/gdrive/backup", json={"keep": 1})
    assert response.status_code == 200
    assert response.json()["file_id"] == "drive-1"
    assert response.json()["pruned"] == []


async def test_backup_reports_upload_failure(client, db_session, monkeypatch):
    await _connect(db_session)
    _stub_archive(monkeypatch)

    fake = _FakeAsyncClient([
        _token(),
        _backup_folder_lookup(),
        _response(500, {"error": {"message": "Drive is unwell"}}),
    ])
    monkeypatch.setattr(gdrive.httpx, "AsyncClient", fake)

    response = await client.post("/api/gdrive/backup", json={})
    assert response.status_code == 502
    assert "Drive is unwell" in response.json()["detail"]


async def test_keep_must_be_at_least_one(client, db_session):
    """keep=0 would delete every archive; the schema must reject it."""
    await _connect(db_session)
    response = await client.post("/api/gdrive/backup", json={"keep": 0})
    assert response.status_code == 422


# --------------------------------------------------------------------------
# Listing backups
# --------------------------------------------------------------------------


async def test_listing_backups_requires_connection(client):
    response = await client.get("/api/gdrive/backups")
    assert response.status_code == 400


async def test_listing_returns_archives_newest_first(client, db_session, monkeypatch):
    await _connect(db_session)

    fake = _FakeAsyncClient([
        _token(),
        _backup_folder_lookup(),
        _backup_list([
            "typecast-backup-20260801-120000.zip",
            "typecast-backup-20260805-120000.zip",
        ]),
    ])
    monkeypatch.setattr(gdrive.httpx, "AsyncClient", fake)

    response = await client.get("/api/gdrive/backups")
    assert response.status_code == 200
    names = [f["name"] for f in response.json()]
    assert names == [
        "typecast-backup-20260805-120000.zip",
        "typecast-backup-20260801-120000.zip",
    ]


async def test_listing_ignores_files_that_are_not_archives(client, db_session, monkeypatch):
    await _connect(db_session)

    fake = _FakeAsyncClient([
        _token(),
        _backup_folder_lookup(),
        _backup_list(["typecast-backup-20260805-120000.zip", "holiday-photos.zip"]),
    ])
    monkeypatch.setattr(gdrive.httpx, "AsyncClient", fake)

    response = await client.get("/api/gdrive/backups")
    names = [f["name"] for f in response.json()]
    assert names == ["typecast-backup-20260805-120000.zip"]


# --------------------------------------------------------------------------
# Restore endpoint
# --------------------------------------------------------------------------


async def test_restore_requires_connection(client):
    response = await client.post(
        "/api/gdrive/restore", json={"file_id": "x", "confirm": True}
    )
    assert response.status_code == 400


async def test_restore_requires_explicit_confirmation(client, db_session, monkeypatch):
    """The destructive path must not run on a default."""
    await _connect(db_session)
    called = False

    async def fake_restore(content):
        nonlocal called
        called = True
        return backup_service.Summary(mode="replace")

    monkeypatch.setattr(gdrive_api, "restore_backup_archive", fake_restore)

    response = await client.post("/api/gdrive/restore", json={"file_id": "id-x"})
    assert response.status_code == 400
    assert "confirm" in response.json()["detail"]
    assert called is False


async def test_restore_rejects_a_file_that_is_not_a_backup(client, db_session, monkeypatch):
    """A stale id must not let a restore overwrite the DB with a manuscript."""
    await _connect(db_session)
    called = False

    async def fake_restore(content):
        nonlocal called
        called = True
        return backup_service.Summary(mode="replace")

    monkeypatch.setattr(gdrive_api, "restore_backup_archive", fake_restore)

    fake = _FakeAsyncClient([
        _token(),
        _backup_folder_lookup(),
        _backup_list(["typecast-backup-20260805-120000.zip"]),
    ])
    monkeypatch.setattr(gdrive.httpx, "AsyncClient", fake)

    response = await client.post(
        "/api/gdrive/restore", json={"file_id": "some-other-file", "confirm": True}
    )
    assert response.status_code == 404
    assert called is False


async def test_restore_downloads_and_applies_the_archive(client, db_session, monkeypatch):
    await _connect(db_session)
    name = "typecast-backup-20260805-120000.zip"
    seen: dict[str, bytes] = {}

    async def fake_restore(content):
        seen["content"] = content
        return backup_service.Summary(mode="replace", files_written=7)

    monkeypatch.setattr(gdrive_api, "restore_backup_archive", fake_restore)

    fake = _FakeAsyncClient([
        _token(),
        _backup_folder_lookup(),
        _backup_list([name]),
        _response(200, content=b"archive-bytes"),
    ])
    monkeypatch.setattr(gdrive.httpx, "AsyncClient", fake)

    response = await client.post(
        "/api/gdrive/restore", json={"file_id": f"id-{name}", "confirm": True}
    )
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "restored"
    assert body["name"] == name
    assert body["files_restored"] == 7
    assert seen["content"] == b"archive-bytes"


async def test_restore_reports_a_corrupt_archive(client, db_session, monkeypatch):
    await _connect(db_session)
    name = "typecast-backup-20260805-120000.zip"

    async def fake_restore(content):
        raise backup_service.BackupError("Invalid ZIP file")

    monkeypatch.setattr(gdrive_api, "restore_backup_archive", fake_restore)

    fake = _FakeAsyncClient([
        _token(),
        _backup_folder_lookup(),
        _backup_list([name]),
        _response(200, content=b"junk"),
    ])
    monkeypatch.setattr(gdrive.httpx, "AsyncClient", fake)

    response = await client.post(
        "/api/gdrive/restore", json={"file_id": f"id-{name}", "confirm": True}
    )
    assert response.status_code == 400
    assert "Invalid ZIP" in response.json()["detail"]


async def test_restore_reports_a_download_failure(client, db_session, monkeypatch):
    await _connect(db_session)
    name = "typecast-backup-20260805-120000.zip"

    async def fake_restore(content):
        raise AssertionError("must not restore after a failed download")

    monkeypatch.setattr(gdrive_api, "restore_backup_archive", fake_restore)

    fake = _FakeAsyncClient([
        _token(),
        _backup_folder_lookup(),
        _backup_list([name]),
        _response(500, {"error": {"message": "download broke"}}),
    ])
    monkeypatch.setattr(gdrive.httpx, "AsyncClient", fake)

    response = await client.post(
        "/api/gdrive/restore", json={"file_id": f"id-{name}", "confirm": True}
    )
    assert response.status_code == 502
