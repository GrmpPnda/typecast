"""Backup archive construction, restoration, and import.

Used by the local download/upload endpoints and the Google Drive endpoints, so
all of them build and consume byte-identical archives.

Archive format version 2 (current) is database-neutral: a manifest, one JSON
file of rows per table, and the uploads directory. It restores into SQLite or
Postgres. Version 1 was a copy of the SQLite database file plus uploads; those
archives can still be restored, but only onto SQLite, because nothing else can
read the file.

Three operations:

* ``build_backup_archive`` writes a version 2 archive from any database.
* ``restore_backup_archive`` replaces everything with an archive's contents.
  For recovering an install from its own backup.
* ``import_backup_archive`` adds an archive's works to an existing install
  under one account, leaving its accounts and secrets alone. For moving works
  from one install to another, for example from a local SQLite install to a
  hosted Postgres one.
"""

from __future__ import annotations

import io
import json
import logging
import shutil
import zipfile
from datetime import UTC, datetime
from pathlib import Path

from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy.exc import DBAPIError

from app import paths
from app.config import settings
from app.db.engine import ALEMBIC_INI, engine
from app.db.engine import BACKEND_DIR as _ENGINE_BACKEND_DIR
from app.services import portable

logger = logging.getLogger(__name__)

# Re-exported for callers and tests that already import them from here. The
# resolution itself lives in app.paths so every upload path agrees.
BACKEND_DIR = paths.BACKEND_DIR
resolve_data_dir = paths.resolve_data_dir

DATA_DIR = paths.DATA_DIR
DB_PATH = paths.DB_PATH
UPLOAD_DIR = paths.UPLOAD_DIR

ARCHIVE_DB_NAME = "typecast.db"  # version 1 archives only
MANIFEST_NAME = "manifest.json"
FORMAT_NAME = "typecast-archive"
FORMAT_VERSION = 2
BACKUP_PREFIX = "typecast-backup-"
BACKUP_MIME = "application/zip"

_MAX_LISTED = 20


class BackupError(Exception):
    """Archive could not be built, read, or loaded. The message is shown to the user."""


class BackupUnsupportedError(BackupError):
    """This server cannot perform the operation at all, as opposed to a bad archive.

    The API answers 501 for it rather than 400. Raised for a version 1 archive
    on Postgres, since that format is a SQLite database file.
    """


Summary = portable.LoadSummary


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


# --- schema revision -------------------------------------------------------------


def _current_revision(sync_conn) -> str | None:
    return MigrationContext.configure(sync_conn).get_current_revision()


def _script_directory() -> ScriptDirectory:
    config = Config(str(ALEMBIC_INI))
    config.set_main_option("script_location", str(_ENGINE_BACKEND_DIR / "alembic"))
    return ScriptDirectory.from_config(config)


def _check_revision(archive_rev: str | None, target_rev: str | None) -> None:
    """Refuse archives this schema cannot hold.

    Equal revisions always load. An archive from an *older* revision loads with
    columns adapted (new columns take their defaults, removed ones are dropped
    and reported). An archive from a revision this code has never seen came
    from a newer Typecast and is refused rather than guessed at.
    """
    if archive_rev == target_rev or archive_rev is None or target_rev is None:
        return
    script = _script_directory()
    known = {rev.revision for rev in script.walk_revisions()}
    if archive_rev not in known:
        raise BackupError(
            "This backup was made by a newer version of Typecast "
            f"(schema {archive_rev}). Update this install, then try again."
        )
    ancestors = {rev.revision for rev in script.iterate_revisions(target_rev, "base")}
    if archive_rev not in ancestors:
        raise BackupError(
            f"This backup's schema ({archive_rev}) is not an earlier version of this "
            f"install's schema ({target_rev}), so it cannot be loaded safely."
        )
    logger.info("Loading an archive from older schema %s into %s", archive_rev, target_rev)


# --- building ----------------------------------------------------------------------


async def build_backup_archive() -> tuple[bytes, str]:
    """Write a version 2 archive of every table and every upload.

    Works on SQLite and Postgres alike. On Postgres the read runs under
    REPEATABLE READ so every table comes from the same snapshot.
    """
    from app.services import auth as auth_service

    logger.info(
        "Building backup archive (dialect=%s, uploads=%s)", engine.dialect.name, UPLOAD_DIR
    )
    async with engine.connect() as conn:
        if engine.dialect.name == "postgresql":
            conn = await conn.execution_options(isolation_level="REPEATABLE READ")
        async with conn.begin():
            rows = await portable.export_rows(conn)
            revision = await conn.run_sync(_current_revision)

    manifest = {
        "format": FORMAT_NAME,
        "format_version": FORMAT_VERSION,
        "alembic_revision": revision,
        "exported_at": datetime.now(UTC).isoformat(),
        "source_dialect": engine.dialect.name,
        # Recorded so a restore can refuse to install a single-user archive's
        # account, which has the published default password, on a multi-user
        # deployment.
        "source_auth_mode": auth_service.AUTH_MODE,
        "tables": {name: len(table_rows) for name, table_rows in rows.items()},
    }

    buf = io.BytesIO()
    file_count = 0
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for name, table_rows in rows.items():
            zf.writestr(f"data/{name}.json", json.dumps(table_rows, ensure_ascii=False))
        if UPLOAD_DIR.exists():
            for file in sorted(UPLOAD_DIR.rglob("*")):
                if file.is_file():
                    zf.write(file, f"uploads/{file.relative_to(UPLOAD_DIR).as_posix()}")
                    file_count += 1
        manifest["upload_files"] = file_count
        zf.writestr(MANIFEST_NAME, json.dumps(manifest, indent=2))

    data = buf.getvalue()
    filename = backup_filename()
    logger.info(
        "Built backup archive %s (%d bytes, %d row(s), %d upload file(s))",
        filename, len(data), sum(manifest["tables"].values()), file_count,
    )
    return data, filename


# --- reading ---------------------------------------------------------------------------


def _open_zip(content: bytes) -> zipfile.ZipFile:
    try:
        return zipfile.ZipFile(io.BytesIO(content), "r")
    except zipfile.BadZipFile as exc:
        logger.error("Archive is not a valid ZIP: %s", exc)
        raise BackupError("Invalid ZIP file") from exc


def _read_manifest(zf: zipfile.ZipFile) -> dict:
    try:
        manifest = json.loads(zf.read(MANIFEST_NAME))
    except (KeyError, ValueError) as exc:
        raise BackupError("Invalid backup: the manifest is missing or unreadable") from exc
    if manifest.get("format") != FORMAT_NAME:
        raise BackupError("Invalid backup: this is not a Typecast archive")
    version = manifest.get("format_version")
    if not isinstance(version, int) or version > FORMAT_VERSION:
        raise BackupError(
            f"This backup uses archive format {version}, which needs a newer version of "
            "Typecast."
        )
    return manifest


def _read_rows(zf: zipfile.ZipFile, summary: Summary) -> dict[str, list[dict]]:
    raw: dict[str, list[dict]] = {}
    for name in zf.namelist():
        if name.startswith("data/") and name.endswith(".json"):
            table = name[len("data/") : -len(".json")]
            try:
                raw[table] = json.loads(zf.read(name))
            except ValueError as exc:
                raise BackupError(f"Invalid backup: {name} is not valid JSON") from exc
    try:
        decoded = portable.decode_rows(raw, summary)
    except portable.PortableError as exc:
        raise BackupError(str(exc)) from exc

    problems = portable.validate_rows(decoded, engine.dialect.name, limit=_MAX_LISTED)
    if problems:
        logger.error("Archive rows rejected by validation: %s", problems)
        raise BackupError(
            "This database would reject some of the archive's data:\n- "
            + "\n- ".join(problems)
        )
    return decoded


def _upload_entries(zf: zipfile.ZipFile):
    """(archive name, destination under UPLOAD_DIR) for every safe upload entry."""
    root = UPLOAD_DIR.resolve()
    for name in zf.namelist():
        if not name.startswith("uploads/") or name.endswith("/"):
            continue
        relative = name[len("uploads/") :]
        dest = (UPLOAD_DIR / relative).resolve()
        # A hand-edited archive must not write outside the uploads directory.
        if dest != root and root not in dest.parents:
            logger.warning("Skipping suspicious archive entry: %s", name)
            continue
        yield name, relative


def _swap_directory_contents(target: Path, incoming: Path, parking: Path) -> None:
    """Replace ``target``'s entries with ``incoming``'s, keeping ``target`` itself.

    Moves entries rather than renaming the directory: ``target`` may be a mount
    point or a directory from a read-only image layer, and neither can be
    renamed. ``shutil.move`` renames where it can and copies where it cannot,
    for example across devices. Current entries are parked so the swap can be
    reversed, and a failure partway through reverses itself before re-raising.
    """
    emptied = False
    try:
        for entry in list(target.iterdir()):
            shutil.move(str(entry), str(parking / entry.name))
        emptied = True
        for entry in list(incoming.iterdir()):
            shutil.move(str(entry), str(target / entry.name))
    except BaseException:
        # Before the target was emptied it holds only old entries, which must
        # stay; after, it holds only new ones, which must go.
        _restore_parked(target, parking, clear_target=emptied)
        raise


def _restore_parked(target: Path, parking: Path, *, clear_target: bool) -> None:
    """Undo _swap_directory_contents: bring the parked entries back."""
    if clear_target:
        for entry in list(target.iterdir()):
            if entry.is_dir() and not entry.is_symlink():
                shutil.rmtree(entry)
            else:
                entry.unlink()
    for entry in list(parking.iterdir()):
        shutil.move(str(entry), str(target / entry.name))


def _can_decrypt(ciphertext: str) -> bool:
    from app.services.crypto import decrypt

    try:
        decrypt(ciphertext)
    except Exception:  # noqa: BLE001 - any failure means this install cannot use it
        return False
    return True


def _db_error(exc: DBAPIError) -> BackupError:
    detail = str(getattr(exc, "orig", exc)).splitlines()[0]
    logger.error("Database rejected the archive: %s", detail)
    return BackupError(f"The database rejected the archive's data: {detail}")


# --- restoring (replace) ------------------------------------------------------------------


async def restore_backup_archive(content: bytes) -> Summary:
    """Replace every table and the uploads directory from an archive.

    Destructive by design. The uploads are staged first and swapped in only
    after the database commit, so a rejected archive changes nothing.
    """
    logger.info("Restoring from backup archive (%d bytes)", len(content))
    with _open_zip(content) as zf:
        names = set(zf.namelist())
        if MANIFEST_NAME in names:
            return await _restore_v2(zf)
        if ARCHIVE_DB_NAME in names:
            return await _restore_v1(zf)
    raise BackupError("Invalid backup: this is not a Typecast archive")


async def _restore_v2(zf: zipfile.ZipFile) -> Summary:
    from app.services import auth as auth_service

    manifest = _read_manifest(zf)
    if manifest.get("source_auth_mode") == "local" and auth_service.AUTH_MODE == "multi":
        raise BackupError(
            "This backup comes from a single-user install, whose account uses the "
            "published default password. Restoring it would replace this server's "
            "accounts with that one. Use 'Import into my account' instead."
        )

    summary = Summary(mode="replace")
    decoded = _read_rows(zf, summary)

    staging = DATA_DIR / ".uploads-incoming"
    retired = DATA_DIR / ".uploads-retired"
    for scratch in (staging, retired):
        if scratch.exists():
            shutil.rmtree(scratch)
    staging.mkdir(parents=True)
    retired.mkdir(parents=True)
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

    swapped = False
    try:
        for name, relative in _upload_entries(zf):
            dest = staging / relative
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(zf.read(name))
            summary.files_written += 1

        async with engine.connect() as conn:
            trans = await conn.begin()
            try:
                _check_revision(
                    manifest.get("alembic_revision"), await conn.run_sync(_current_revision)
                )
                await portable.replace_rows(conn, decoded, summary, _can_decrypt)
                # Install the files *before* committing, so a failure here rolls
                # the database back too. The old order committed first and then
                # renamed the uploads directory, which overlayfs (a directory
                # from an image layer), a mount point at uploads/, and some
                # network filesystems all refuse, leaving the new database with
                # the old files.
                _swap_directory_contents(UPLOAD_DIR, staging, retired)
                swapped = True
                await trans.commit()
            except BaseException:
                await trans.rollback()
                raise
    except BaseException as exc:
        if swapped:
            # The swap finished but the commit did not: the database rolled
            # back, so the files must too.
            _restore_parked(UPLOAD_DIR, retired, clear_target=True)
            logger.warning("Restore failed after the uploads were swapped; put the old ones back")
        shutil.rmtree(staging, ignore_errors=True)
        shutil.rmtree(retired, ignore_errors=True)
        if isinstance(exc, DBAPIError):
            raise _db_error(exc) from exc
        raise

    shutil.rmtree(staging, ignore_errors=True)
    shutil.rmtree(retired, ignore_errors=True)
    logger.info(
        "Restore complete: %d row(s), %d upload file(s), %d secret(s) dropped",
        summary.total_rows, summary.files_written, summary.secrets_dropped,
    )
    return summary


async def _restore_v1(zf: zipfile.ZipFile) -> Summary:
    """Version 1: overwrite the SQLite file and the uploads directory."""
    if settings.is_postgres:
        message = (
            "This is an older backup, made before archives became database-neutral. "
            "It is a copy of a SQLite database file, so only a SQLite install can "
            "restore it. Restore it into a SQLite install, download a new backup there, "
            "and import that here."
        )
        logger.error("Legacy restore refused on Postgres")
        raise BackupUnsupportedError(message)

    summary = Summary(mode="replace")
    # Close pooled connections before overwriting the database file.
    await engine.dispose()

    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    DB_PATH.write_bytes(zf.read(ARCHIVE_DB_NAME))

    if UPLOAD_DIR.exists():
        shutil.rmtree(UPLOAD_DIR)
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    for name, relative in _upload_entries(zf):
        dest = UPLOAD_DIR / relative
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(zf.read(name))
        summary.files_written += 1

    logger.info("Legacy restore complete (%d upload file(s))", summary.files_written)
    return summary


# --- importing (merge) ---------------------------------------------------------------------


async def import_backup_archive(
    content: bytes, owner_id, *, dry_run: bool = False
) -> Summary:
    """Add an archive's works to this install, owned by ``owner_id``.

    Accounts and secrets are not imported. Upload files are added only where
    the path is free; an existing file with different contents is kept and
    reported. The database work commits last, after the files are written, so a
    failure rolls back both. ``dry_run`` runs every check and the inserts, then
    rolls back and writes no files.
    """
    logger.info(
        "Importing archive into account %s (%d bytes, dry_run=%s)",
        owner_id, len(content), dry_run,
    )
    with _open_zip(content) as zf:
        names = set(zf.namelist())
        if MANIFEST_NAME not in names:
            if ARCHIVE_DB_NAME in names:
                raise BackupError(
                    "This is an older backup format, which can only be restored, not "
                    "imported. Restore it into a SQLite install, download a new backup "
                    "there, and import that."
                )
            raise BackupError("Invalid backup: this is not a Typecast archive")

        manifest = _read_manifest(zf)
        summary = Summary(mode="import", dry_run=dry_run)
        decoded = _read_rows(zf, summary)

        planned = []
        for name, relative in _upload_entries(zf):
            dest = UPLOAD_DIR / relative
            data = zf.read(name)
            if dest.exists():
                if dest.read_bytes() == data:
                    summary.files_unchanged += 1
                elif len(summary.file_conflicts) < _MAX_LISTED:
                    summary.file_conflicts.append(relative)
                continue
            planned.append((dest, data))

        written: list[Path] = []
        async with engine.connect() as conn:
            trans = await conn.begin()
            try:
                _check_revision(
                    manifest.get("alembic_revision"), await conn.run_sync(_current_revision)
                )
                await portable.merge_rows(conn, decoded, summary, owner_id)
                if dry_run:
                    summary.files_written = len(planned)
                    await trans.rollback()
                    logger.info("Dry run complete; rolled back")
                    return summary
                for dest, data in planned:
                    dest.parent.mkdir(parents=True, exist_ok=True)
                    dest.write_bytes(data)
                    written.append(dest)
                await trans.commit()
            except BaseException as exc:
                await trans.rollback()
                for path in written:
                    path.unlink(missing_ok=True)
                if isinstance(exc, portable.PortableError):
                    raise BackupError(str(exc)) from exc
                if isinstance(exc, DBAPIError):
                    raise _db_error(exc) from exc
                raise

    summary.files_written = len(written)
    logger.info(
        "Import complete: %d row(s), %d file(s) written, %d unchanged, %d conflict(s)",
        summary.total_rows, summary.files_written, summary.files_unchanged,
        len(summary.file_conflicts),
    )
    return summary
