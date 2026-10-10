"""Archive format version 2: database-neutral backup, restore, and import.

Two installs are simulated with two separate databases and upload directories.
The source is the shared test engine; the target is a fresh SQLite file. Both
seed their own built-in profiles with different IDs, which is the situation a
real move from a local install to a hosted one creates.

These run on SQLite only. The Postgres side was exercised against a real
PostgreSQL 16 server on the cloud desktop (see CLAUDE.md); the encoding is
driven by column type, so nothing here depends on which dialect produced it.
"""

from __future__ import annotations

import io
import json
import uuid
import zipfile
from collections.abc import AsyncGenerator
from datetime import UTC, datetime

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import event, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.api.deps import get_current_user
from app.db.base import Base
from app.db.engine import get_db
from app.main import create_app
from app.models.chapter import Chapter
from app.models.codex import CodexEntry, EntryType
from app.models.codex_association import CodexAssociation
from app.models.codex_image import CodexImage
from app.models.comment import Comment
from app.models.config import AppConfig
from app.models.conversation import Conversation, ConversationMessage
from app.models.font import Font
from app.models.image import Image
from app.models.profile import Profile, ProfileFormat
from app.models.scene import Scene
from app.models.section import Section, SectionPlacement, SectionType
from app.models.series import Series
from app.models.user import User
from app.models.work import Work
from app.services import backup as backup_service
from app.services import portable
from app.services.auth import hash_password
from app.services.crypto import encrypt

# --- two installs ----------------------------------------------------------------


def _use_install(monkeypatch, eng, data_dir):
    """Point the backup service at one install's database and uploads."""
    uploads = data_dir / "uploads"
    uploads.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(backup_service, "engine", eng)
    monkeypatch.setattr(backup_service, "DATA_DIR", data_dir)
    monkeypatch.setattr(backup_service, "DB_PATH", data_dir / "typecast.db")
    monkeypatch.setattr(backup_service, "UPLOAD_DIR", uploads)
    return uploads


@pytest_asyncio.fixture
async def target_engine(tmp_path):
    """A second, empty install with foreign keys enforced like the first."""
    eng = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'target.db'}")

    @event.listens_for(eng.sync_engine, "connect")
    def _fk(dbapi_connection, _record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    async with eng.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield eng
    await eng.dispose()


async def _add(session_factory, *objects):
    async with session_factory() as session:
        session.add_all(objects)
        await session.commit()


async def _builtin_profile(session_factory, name="Standard ePub") -> uuid.UUID:
    profile = Profile(id=uuid.uuid4(), name=name, format=ProfileFormat.EPUB, is_builtin=True)
    await _add(session_factory, profile)
    return profile.id


async def _seed_source(session_factory, owner: User, uploads) -> dict:
    """One row in every table, wired together the way the app wires them."""
    builtin = await _builtin_profile(session_factory)
    custom = Profile(id=uuid.uuid4(), name="Paperback 5x8", format=ProfileFormat.PDF)
    series = Series(id=uuid.uuid4(), title="Below Decks", user_id=owner.id)
    work = Work(
        id=uuid.uuid4(), title="Earthfall", author="B. S.", user_id=owner.id,
        series_id=series.id, default_profile_id=builtin,
    )
    second = Work(
        id=uuid.uuid4(), title="Nimrod", author="B. S.", user_id=owner.id,
        default_profile_id=custom.id,
    )
    chapter = Chapter(id=uuid.uuid4(), work_id=work.id, title="One", number=1, sort_order=0)
    scene = Scene(
        id=uuid.uuid4(), chapter_id=chapter.id, sort_order=0,
        content=f"Text ![map](/uploads/images/{work.id}/map.png)",
    )
    comment = Comment(id=uuid.uuid4(), scene_id=scene.id, anchor_text="Text", content="Hm.")
    section = Section(
        id=uuid.uuid4(), work_id=work.id, section_type=SectionType.DEDICATION,
        placement=SectionPlacement.FRONT_MATTER, content="For K.",
    )
    image = Image(
        id=uuid.uuid4(), work_id=work.id, filename="map.png", original_name="map.png",
        mime_type="image/png", size_bytes=3,
    )
    entry = CodexEntry(id=uuid.uuid4(), name="Alice", entry_type=EntryType.CHARACTER)
    association = CodexAssociation(
        id=uuid.uuid4(), codex_entry_id=entry.id, target_type="work", target_id=work.id
    )
    codex_image = CodexImage(
        id=uuid.uuid4(), codex_entry_id=entry.id, filename="alice.png",
        original_name="alice.png", mime_type="image/png", size_bytes=3, is_primary=True,
    )
    conversation = Conversation(id=uuid.uuid4(), user_id=owner.id, work_id=work.id)
    message = ConversationMessage(
        id=uuid.uuid4(), conversation_id=conversation.id, role="user", content="Hello"
    )
    font = Font(
        id=uuid.uuid4(), filename="serif.ttf", original_name="Serif.ttf",
        family_name="Serif", mime_type="font/ttf", size_bytes=3,
    )
    configs = [
        AppConfig(key="ai_provider", value="anthropic", is_secret=False),
        AppConfig(key="anthropic_api_key", value=encrypt("sk-ant-real"), is_secret=True),
        AppConfig(key="gdrive_folder_id", value="folder-xyz", is_secret=False),
    ]
    # Parents before children: these models declare no relationship(), so the
    # ORM does not order the inserts by foreign key on its own.
    for batch in (
        (custom, series, entry, font, *configs),
        (work, second),
        (chapter, section, image, association, codex_image, conversation),
        (scene, message),
        (comment,),
    ):
        await _add(session_factory, *batch)

    (uploads / "images" / str(work.id)).mkdir(parents=True)
    (uploads / "images" / str(work.id) / "map.png").write_bytes(b"png")
    (uploads / "codex" / str(entry.id)).mkdir(parents=True)
    (uploads / "codex" / str(entry.id) / "alice.png").write_bytes(b"png")
    (uploads / "fonts").mkdir()
    (uploads / "fonts" / "serif.ttf").write_bytes(b"ttf")

    return {"work": work.id, "second": second.id, "builtin": builtin, "custom": custom.id}


async def _snapshot(eng) -> dict[str, list[dict]]:
    async with eng.connect() as conn:
        rows = await portable.export_rows(conn)
    return {name: sorted(r, key=lambda row: str(row.get("id"))) for name, r in rows.items()}


# --- format ------------------------------------------------------------------------


def test_every_table_has_a_merge_role():
    """A new model must declare whether its rows travel with a user's works."""
    assert set(portable.TABLE_ROLES) == set(Base.metadata.tables)


@pytest.mark.parametrize(
    ("column", "value"),
    [
        (Work.__table__.c.id, uuid.uuid4()),
        (Work.__table__.c.status, Work.__table__.c.status.type.enum_class["DRAFT"]),
        (Profile.__table__.c.is_builtin, True),
        (Work.__table__.c.created_at, datetime(2026, 1, 2, 3, 4, 5, tzinfo=UTC)),
        (Work.__table__.c.title, "Earthfall"),
    ],
)
def test_values_survive_a_json_round_trip(column, value):
    encoded = portable.encode_value(column, value)
    assert json.loads(json.dumps(encoded)) == encoded
    assert portable.decode_value(column, encoded) == value


def test_naive_datetimes_are_read_as_utc():
    """SQLite returns naive values; its CURRENT_TIMESTAMP is UTC."""
    column = Work.__table__.c.created_at
    encoded = portable.encode_value(column, datetime(2026, 1, 2, 3, 4, 5))
    assert encoded.endswith("+00:00")


def test_postgres_limits_are_checked_before_writing():
    """SQLite ignores VARCHAR lengths and stores NUL bytes; Postgres refuses both."""
    rows = {"works": [{"id": "w", "title": "x" * 501, "author": "a\x00b"}]}
    problems = portable.validate_rows(rows, "postgresql")
    assert any("title" in p and "limit is 500" in p for p in problems)
    assert any("author" in p and "NUL" in p for p in problems)
    assert portable.validate_rows(rows, "sqlite") == []


async def test_archive_has_a_manifest_rows_and_uploads(engine, session_factory, test_user,
                                                        tmp_path, monkeypatch):
    uploads = _use_install(monkeypatch, engine, tmp_path / "source")
    await _seed_source(session_factory, test_user, uploads)

    content, filename = await backup_service.build_backup_archive()

    assert filename.startswith("typecast-backup-") and filename.endswith(".zip")
    with zipfile.ZipFile(io.BytesIO(content)) as zf:
        names = set(zf.namelist())
        manifest = json.loads(zf.read("manifest.json"))
        works = json.loads(zf.read("data/works.json"))
    assert manifest["format"] == "typecast-archive"
    assert manifest["format_version"] == 2
    assert manifest["source_dialect"] == "sqlite"
    assert manifest["tables"]["works"] == 2
    assert manifest["upload_files"] == 3
    assert "typecast.db" not in names, "v2 must not depend on a database file"
    assert {w["title"] for w in works} == {"Earthfall", "Nimrod"}
    assert "uploads/fonts/serif.ttf" in names


# --- restore (replace) -------------------------------------------------------------------


async def test_restore_round_trips_every_row(engine, session_factory, test_user,
                                             tmp_path, monkeypatch):
    uploads = _use_install(monkeypatch, engine, tmp_path / "source")
    ids = await _seed_source(session_factory, test_user, uploads)
    before = await _snapshot(engine)
    content, _ = await backup_service.build_backup_archive()

    # Diverge from the archive: delete a work, add a stray file.
    async with session_factory() as session:
        await session.delete(await session.get(Work, ids["second"]))
        await session.commit()
    (uploads / "stray.txt").write_bytes(b"should not survive")

    summary = await backup_service.restore_backup_archive(content)

    assert await _snapshot(engine) == before
    assert summary.files_written == 3
    assert not (uploads / "stray.txt").exists()
    assert (uploads / "fonts" / "serif.ttf").read_bytes() == b"ttf"


async def test_restore_drops_secrets_this_install_cannot_decrypt(
    engine, session_factory, test_user, tmp_path, monkeypatch
):
    """A different SECRET_KEY makes them unreadable, and every read would raise."""
    from app.config import settings

    uploads = _use_install(monkeypatch, engine, tmp_path / "source")
    await _seed_source(session_factory, test_user, uploads)
    content, _ = await backup_service.build_backup_archive()

    monkeypatch.setattr(settings, "SECRET_KEY", "a-different-key-entirely")
    summary = await backup_service.restore_backup_archive(content)

    assert summary.secrets_dropped == 1
    assert "anthropic_api_key" in summary.skipped_config
    async with session_factory() as session:
        keys = set((await session.execute(select(AppConfig.key))).scalars())
    assert "anthropic_api_key" not in keys
    assert "ai_provider" in keys


async def test_restore_refuses_a_single_user_archive_on_a_multi_user_server(
    engine, session_factory, test_user, tmp_path, monkeypatch
):
    """It would install an administrator whose password is published."""
    uploads = _use_install(monkeypatch, engine, tmp_path / "source")
    await _seed_source(session_factory, test_user, uploads)
    content, _ = await backup_service.build_backup_archive()
    before = await _snapshot(engine)

    monkeypatch.setattr("app.services.auth.AUTH_MODE", "multi")
    with pytest.raises(backup_service.BackupError, match="Import into my account"):
        await backup_service.restore_backup_archive(content)
    assert await _snapshot(engine) == before


async def test_a_rejected_restore_changes_nothing(engine, session_factory, test_user,
                                                  tmp_path, monkeypatch):
    uploads = _use_install(monkeypatch, engine, tmp_path / "source")
    await _seed_source(session_factory, test_user, uploads)
    content, _ = await backup_service.build_backup_archive()
    before = await _snapshot(engine)

    broken = _rewrite(content, "data/works.json", lambda rows: [
        {**r, "status": "NOT_A_STATUS"} for r in rows
    ])
    with pytest.raises(backup_service.BackupError, match="cannot read"):
        await backup_service.restore_backup_archive(broken)

    assert await _snapshot(engine) == before
    assert (uploads / "fonts" / "serif.ttf").exists()
    assert not (tmp_path / "source" / ".uploads-incoming").exists()


async def test_restore_skips_path_traversal_entries(engine, session_factory, test_user,
                                                    tmp_path, monkeypatch):
    uploads = _use_install(monkeypatch, engine, tmp_path / "source")
    await _seed_source(session_factory, test_user, uploads)
    content, _ = await backup_service.build_backup_archive()

    hostile = _add_entry(content, "uploads/../../escaped.txt", b"pwned")
    await backup_service.restore_backup_archive(hostile)
    assert not (tmp_path / "escaped.txt").exists()


def _rewrite(content: bytes, name: str, change) -> bytes:
    """Copy an archive with one JSON member transformed."""
    out = io.BytesIO()
    with zipfile.ZipFile(io.BytesIO(content)) as src, zipfile.ZipFile(out, "w") as dst:
        for item in src.namelist():
            data = src.read(item)
            if item == name:
                data = json.dumps(change(json.loads(data))).encode()
            dst.writestr(item, data)
    return out.getvalue()


def _add_entry(content: bytes, name: str, data: bytes) -> bytes:
    out = io.BytesIO()
    with zipfile.ZipFile(io.BytesIO(content)) as src, zipfile.ZipFile(out, "w") as dst:
        for item in src.namelist():
            dst.writestr(item, src.read(item))
        dst.writestr(name, data)
    return out.getvalue()


# --- import (merge) ----------------------------------------------------------------------


async def _move_to_target(engine, session_factory, test_user, target_engine, tmp_path,
                          monkeypatch, *, dry_run=False):
    """Export the seeded source, then import it into the target as a new account."""
    source_uploads = _use_install(monkeypatch, engine, tmp_path / "source")
    ids = await _seed_source(session_factory, test_user, source_uploads)
    content, _ = await backup_service.build_backup_archive()

    target_sessions = async_sessionmaker(target_engine, expire_on_commit=False)
    admin = User(
        id=uuid.uuid4(), email="admin@azure.example", username="admin",
        display_name="Admin", hashed_password=hash_password("x" * 12), is_admin=True,
    )
    await _add(target_sessions, admin)
    target_builtin = await _builtin_profile(target_sessions)

    target_uploads = _use_install(monkeypatch, target_engine, tmp_path / "target")
    summary = await backup_service.import_backup_archive(content, admin.id, dry_run=dry_run)
    return summary, ids, admin, target_builtin, target_sessions, target_uploads, content


async def test_import_moves_works_into_the_importing_account(
    engine, session_factory, test_user, target_engine, tmp_path, monkeypatch
):
    summary, ids, admin, target_builtin, sessions, uploads, _ = await _move_to_target(
        engine, session_factory, test_user, target_engine, tmp_path, monkeypatch
    )

    async with sessions() as session:
        works = {w.id: w for w in (await session.execute(select(Work))).scalars()}
        users = (await session.execute(select(User.email))).scalars().all()
        series_owner = (await session.execute(select(Series.user_id))).scalar_one()
        convo_owner = (await session.execute(select(Conversation.user_id))).scalar_one()
        scene = (await session.execute(select(Scene))).scalar_one()

    # IDs are kept, so references and upload paths in prose stay valid.
    assert set(works) == {ids["work"], ids["second"]}
    assert f"/uploads/images/{ids['work']}/map.png" in scene.content
    # Everything belongs to the importer; the source account did not come along.
    assert users == ["admin@azure.example"]
    assert all(w.user_id == admin.id for w in works.values())
    assert series_owner == admin.id and convo_owner == admin.id
    # Built-ins are matched by name; custom profiles keep their own IDs.
    assert works[ids["work"]].default_profile_id == target_builtin
    assert works[ids["second"]].default_profile_id == ids["custom"]
    assert summary.profiles_remapped == 1
    # Files arrived where the database expects them.
    assert (uploads / "images" / str(ids["work"]) / "map.png").read_bytes() == b"png"
    assert summary.files_written == 3


async def test_import_leaves_secrets_and_drive_settings_behind(
    engine, session_factory, test_user, target_engine, tmp_path, monkeypatch
):
    summary, *_rest = await _move_to_target(
        engine, session_factory, test_user, target_engine, tmp_path, monkeypatch
    )
    sessions = _rest[3]
    async with sessions() as session:
        keys = set((await session.execute(select(AppConfig.key))).scalars())

    assert keys == {"ai_provider"}
    assert {"anthropic_api_key", "gdrive_folder_id"} <= set(summary.skipped_config)


async def test_importing_the_same_archive_twice_is_refused_cleanly(
    engine, session_factory, test_user, target_engine, tmp_path, monkeypatch
):
    _summary, _ids, admin, _b, sessions, uploads, content = await _move_to_target(
        engine, session_factory, test_user, target_engine, tmp_path, monkeypatch
    )
    async with sessions() as session:
        before = len((await session.execute(select(Work))).scalars().all())

    with pytest.raises(backup_service.BackupError, match="already here"):
        await backup_service.import_backup_archive(content, admin.id)

    async with sessions() as session:
        assert len((await session.execute(select(Work))).scalars().all()) == before


async def test_dry_run_checks_everything_and_writes_nothing(
    engine, session_factory, test_user, target_engine, tmp_path, monkeypatch
):
    summary, ids, _admin, _b, sessions, uploads, _ = await _move_to_target(
        engine, session_factory, test_user, target_engine, tmp_path, monkeypatch, dry_run=True
    )

    assert summary.dry_run is True
    assert summary.rows["works"] == 2
    assert summary.files_written == 3, "reports what would be written"
    async with sessions() as session:
        assert (await session.execute(select(Work))).scalars().all() == []
    assert not (uploads / "images" / str(ids["work"])).exists()


async def test_import_keeps_an_existing_file_that_differs(
    engine, session_factory, test_user, target_engine, tmp_path, monkeypatch
):
    (tmp_path / "target" / "uploads" / "fonts").mkdir(parents=True)
    (tmp_path / "target" / "uploads" / "fonts" / "serif.ttf").write_bytes(b"theirs")

    summary, *_ = await _move_to_target(
        engine, session_factory, test_user, target_engine, tmp_path, monkeypatch
    )

    assert summary.file_conflicts == ["fonts/serif.ttf"]
    assert (tmp_path / "target" / "uploads" / "fonts" / "serif.ttf").read_bytes() == b"theirs"


async def test_legacy_archives_cannot_be_imported(engine, tmp_path, monkeypatch):
    _use_install(monkeypatch, engine, tmp_path / "source")
    legacy = io.BytesIO()
    with zipfile.ZipFile(legacy, "w") as zf:
        zf.writestr("typecast.db", b"SQLite format 3\x00")
    with pytest.raises(backup_service.BackupError, match="older backup format"):
        await backup_service.import_backup_archive(legacy.getvalue(), uuid.uuid4())


def test_archives_from_an_unknown_schema_are_refused():
    with pytest.raises(backup_service.BackupError, match="newer version"):
        backup_service._check_revision("ffffffffffff", "b1199ab62ff7")
    backup_service._check_revision("b1199ab62ff7", "b1199ab62ff7")


# --- endpoints ---------------------------------------------------------------------------


def _client_as(session_factory, user: User) -> AsyncClient:
    app = create_app()

    async def override_get_db() -> AsyncGenerator[AsyncSession, None]:
        async with session_factory() as session:
            yield session

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_current_user] = lambda: user
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


@pytest.mark.parametrize(
    ("method", "path"),
    [("get", "/api/backup/backup"), ("post", "/api/backup/restore"),
     ("post", "/api/backup/import"), ("get", "/api/gdrive/backups"),
     ("post", "/api/gdrive/backup"), ("post", "/api/gdrive/restore")],
)
async def test_backup_endpoints_require_an_administrator(session_factory, method, path):
    """These had no authentication at all: anyone could download or wipe the install."""
    member = User(
        id=uuid.uuid4(), email="m@x.example", username="member", display_name="M",
        hashed_password=hash_password("x" * 12), is_admin=False,
    )
    await _add(session_factory, member)
    async with _client_as(session_factory, member) as ac:
        resp = await getattr(ac, method)(path)
    assert resp.status_code == 403, f"{path} returned {resp.status_code}"


async def test_import_endpoint_reports_what_it_did(
    engine, session_factory, test_user, client, tmp_path, monkeypatch
):
    uploads = _use_install(monkeypatch, engine, tmp_path / "source")
    await _seed_source(session_factory, test_user, uploads)
    content, _ = await backup_service.build_backup_archive()

    resp = await client.post(
        "/api/backup/import?dry_run=true",
        files={"file": ("backup.zip", content, "application/zip")},
    )
    assert resp.status_code == 400, "same install: the content is already here"
    assert "already here" in resp.json()["detail"]


# --- failure handling found on the real deployment ------------------------------------


async def test_restore_survives_a_filesystem_that_cannot_rename_directories(
    engine, session_factory, test_user, tmp_path, monkeypatch
):
    """overlayfs refuses to rename a directory from an image layer (EXDEV).

    The first version renamed uploads/ itself after committing, which failed in
    the container and left the new database with the old files. shutil.move
    falls back to copying, which is what the swap now relies on.
    """
    import errno
    import os

    uploads = _use_install(monkeypatch, engine, tmp_path / "source")
    await _seed_source(session_factory, test_user, uploads)
    before = await _snapshot(engine)
    content, _ = await backup_service.build_backup_archive()
    (uploads / "stray.txt").write_bytes(b"gone after restore")

    def no_rename(src, dst, *args, **kwargs):
        raise OSError(errno.EXDEV, "Invalid cross-device link", str(src))

    monkeypatch.setattr(os, "rename", no_rename)
    summary = await backup_service.restore_backup_archive(content)

    assert summary.files_written == 3
    assert await _snapshot(engine) == before
    assert (uploads / "fonts" / "serif.ttf").read_bytes() == b"ttf"
    assert not (uploads / "stray.txt").exists()


async def test_a_failure_while_installing_files_rolls_back_files_and_rows(
    engine, session_factory, test_user, tmp_path, monkeypatch
):
    """The database must never be left committed with the wrong uploads."""
    uploads = _use_install(monkeypatch, engine, tmp_path / "source")
    ids = await _seed_source(session_factory, test_user, uploads)
    content, _ = await backup_service.build_backup_archive()

    # Diverge, so a rollback is distinguishable from a successful restore.
    async with session_factory() as session:
        await session.delete(await session.get(Work, ids["second"]))
        await session.commit()
    (uploads / "fonts" / "serif.ttf").write_bytes(b"edited since the backup")
    before = await _snapshot(engine)
    files_before = {
        p.relative_to(uploads).as_posix(): p.read_bytes()
        for p in uploads.rglob("*") if p.is_file()
    }

    # Let every current entry park, then fail on the first incoming one.
    import shutil

    real_move = shutil.move
    parked = len(list(uploads.iterdir()))
    calls = {"n": 0}

    def flaky_move(src, dst, *args, **kwargs):
        calls["n"] += 1
        if calls["n"] == parked + 1:
            raise OSError("disk full")
        return real_move(src, dst, *args, **kwargs)

    monkeypatch.setattr(backup_service.shutil, "move", flaky_move)
    with pytest.raises(OSError, match="disk full"):
        await backup_service.restore_backup_archive(content)

    assert await _snapshot(engine) == before, "database must roll back"
    files_after = {
        p.relative_to(uploads).as_posix(): p.read_bytes()
        for p in uploads.rglob("*") if p.is_file()
    }
    assert files_after == files_before, "uploads must be put back exactly"
    data_dir = tmp_path / "source"
    assert not (data_dir / ".uploads-incoming").exists()
    assert not (data_dir / ".uploads-retired").exists()


# --- values SQLite stored as text ----------------------------------------------


def _column(table: str, name: str):
    return Base.metadata.tables[table].c[name]


@pytest.mark.parametrize(
    ("table", "column", "stored", "loaded"),
    [
        # The real dev database: profile dimensions held as text, which Postgres
        # rejected with "must be real number, not str".
        ("profiles", "page_width", "8.5", 8.5),
        ("profiles", "margin_inner", " 0.875 ", 0.875),
        ("profiles", "page_width", "", None),
        ("profiles", "page_width", 6.0, 6.0),
        ("chapters", "number", "3", 3),
        ("chapters", "number", "3.0", 3),
        # bool("0") would be True.
        ("profiles", "is_builtin", "0", False),
        ("profiles", "is_builtin", "false", False),
        ("profiles", "is_builtin", "1", True),
        ("profiles", "is_builtin", 0, False),
    ],
)
def test_text_in_typed_columns_is_converted(table, column, stored, loaded):
    from app.services.portable import decode_value

    value = decode_value(_column(table, column), stored)
    assert value == loaded and type(value) is type(loaded)


@pytest.mark.parametrize(
    ("table", "column", "stored"),
    [
        ("profiles", "page_width", "wide"),
        ("chapters", "number", "3.5"),
        ("profiles", "is_builtin", "maybe"),
    ],
)
def test_unreadable_numbers_are_reported_not_loaded(table, column, stored):
    from app.services.portable import PortableError, decode_value

    with pytest.raises(PortableError, match=f"{table}.{column}"):
        decode_value(_column(table, column), stored)


def test_decoded_archive_rows_carry_numbers_not_text():
    """Rows as the dev database exported them. A column created from today's models
    has numeric affinity and would convert "8.5" on write, so the text can only be
    reproduced in the archive, not in a fresh SQLite table."""
    from app.services.portable import LoadSummary, decode_rows

    rows = {"profiles": [{
        "id": "0123456789abcdef0123456789abcdef", "name": "Trade", "format": "PDF",
        "is_builtin": 0, "page_width": "8.5", "page_height": "11.0", "line_height": 1.5,
    }]}
    profile = decode_rows(rows, LoadSummary(mode="import"))["profiles"][0]
    assert (profile["page_width"], profile["page_height"]) == (8.5, 11.0)
    assert all(not isinstance(v, str) for k, v in profile.items() if k.startswith("page_"))
