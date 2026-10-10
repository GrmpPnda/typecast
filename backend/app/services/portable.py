"""Database-neutral table data for backup archives.

Archive format version 2 stores every table as JSON rows, so the same archive
restores into SQLite or Postgres in either direction. Version 1 was a copy of
the SQLite database file, which nothing else can read: that is why backups
returned 501 on Postgres and why a local install could not move to a server.

Values are encoded by *column type*, not by Python type, so decoding is exact:
UUIDs as strings, datetimes as ISO 8601 in UTC, enums by member name. Nothing
here touches the filesystem; ``app.services.backup`` owns the archive and the
uploads directory.

Two ways to load rows:

* ``replace_rows`` empties every table and loads the archive verbatim. For
  restoring an install from its own backup.
* ``merge_rows`` adds the archive's content to an existing install under one
  account. For moving works between installs, which is the case that needs
  care: users are not imported, secrets are not imported, built-in profiles are
  matched by name because each install seeds them with its own IDs, and the
  whole import is refused if any of its content already exists.
"""

from __future__ import annotations

import base64
import enum
import logging
import uuid
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    Enum,
    Float,
    Integer,
    LargeBinary,
    Numeric,
    String,
    Table,
    Uuid,
    delete,
    insert,
    select,
)
from sqlalchemy.ext.asyncio import AsyncConnection

import app.models  # noqa: F401  (registers every table on Base.metadata)
from app.db.base import Base

logger = logging.getLogger(__name__)

# How each table behaves when merging into an existing install. Every table on
# Base.metadata must appear here; a test enforces it, so a new model forces a
# decision about whether its rows travel with a user's works.
CONTENT = "content"  # belongs to the works being moved; refused if already present
SHARED = "shared"  # install-wide (profiles, fonts, settings); added only where absent
ACCOUNT = "account"  # never merged: the importing account owns everything instead

TABLE_ROLES: dict[str, str] = {
    "series": CONTENT,
    "works": CONTENT,
    "chapters": CONTENT,
    "scenes": CONTENT,
    "sections": CONTENT,
    "comments": CONTENT,
    "images": CONTENT,
    "codex_entries": CONTENT,
    "codex_associations": CONTENT,
    "codex_images": CONTENT,
    "conversations": CONTENT,
    "conversation_messages": CONTENT,
    "profiles": SHARED,
    "fonts": SHARED,
    "app_config": SHARED,
    "users": ACCOUNT,
}

# Settings that must not travel between installs on a merge. Secrets are
# encrypted with a key derived from this install's SECRET_KEY, so another
# install cannot decrypt them; the Drive connection is bound to an OAuth
# redirect URI that differs per host and has to be reconnected anyway.
_NON_PORTABLE_CONFIG_PREFIXES = ("gdrive_",)

# Postgres rejects a long IN list less readily than SQLite, but both have
# limits; chunking keeps the existence checks well inside either.
_IN_CHUNK = 500

_TRUE_TEXT = frozenset({"1", "true", "t", "yes", "y", "on"})
_FALSE_TEXT = frozenset({"0", "false", "f", "no", "n", "off"})


class PortableError(Exception):
    """Rows cannot be loaded as given. The message is shown to the user."""


@dataclass
class LoadSummary:
    """What a load did, reported back to the UI."""

    mode: str
    rows: dict[str, int] = field(default_factory=dict)
    profiles_remapped: int = 0
    skipped_config: list[str] = field(default_factory=list)
    secrets_dropped: int = 0
    dropped_columns: list[str] = field(default_factory=list)
    # Filled in by app.services.backup, which handles the uploads.
    files_written: int = 0
    files_unchanged: int = 0
    file_conflicts: list[str] = field(default_factory=list)
    dry_run: bool = False

    @property
    def total_rows(self) -> int:
        return sum(self.rows.values())


def tables_in_load_order() -> list[Table]:
    """Parents before children, so foreign keys resolve as rows go in."""
    return list(Base.metadata.sorted_tables)


# --- encoding ----------------------------------------------------------------


def encode_value(column, value: Any) -> Any:
    """Turn a database value into something json.dumps accepts, losslessly."""
    if value is None:
        return None
    col_type = column.type
    if isinstance(col_type, Enum):
        return value.name if isinstance(value, enum.Enum) else str(value)
    if isinstance(col_type, Uuid) or isinstance(value, uuid.UUID):
        return str(value)
    if isinstance(value, datetime):
        # SQLite returns naive values even for timezone=True columns, and its
        # CURRENT_TIMESTAMP is UTC, so naive means UTC here.
        aware = value if value.tzinfo else value.replace(tzinfo=UTC)
        return aware.astimezone(UTC).isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, (bytes, bytearray, memoryview)):
        return {"$bytes": base64.b64encode(bytes(value)).decode()}
    return value


def decode_value(column, value: Any) -> Any:
    """Inverse of encode_value, driven by the target column's type."""
    if value is None:
        return None
    col_type = column.type
    try:
        if isinstance(col_type, Enum):
            enum_class = col_type.enum_class
            return enum_class[value] if enum_class is not None else value
        if isinstance(col_type, Uuid):
            return uuid.UUID(str(value))
        if isinstance(col_type, DateTime):
            parsed = datetime.fromisoformat(value)
            return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)
        if isinstance(col_type, Date):
            return date.fromisoformat(value)
        if isinstance(col_type, Boolean):
            if isinstance(value, str):
                # bool("0") is True; SQLite can hand back booleans as text.
                lowered = value.strip().lower()
                if lowered in _FALSE_TEXT:
                    return False
                if lowered in _TRUE_TEXT:
                    return True
                raise ValueError(value)
            return bool(value)
        # SQLite keeps whatever was written, so a numeric column can hold "8.5" as
        # text (the dev database's profile dimensions do). Postgres rejects a
        # string for a number, so convert by the column's type.
        # Float is not a Numeric subclass on SQLAlchemy 2.1, so name all three.
        if isinstance(col_type, (Numeric, Float, Integer)) and isinstance(value, str):
            if not value.strip() and column.nullable:
                return None
            number = float(value)
            if isinstance(col_type, Integer):
                if not number.is_integer():
                    raise ValueError(value)
                return int(number)
            if isinstance(col_type, Float) or not col_type.asdecimal:
                return number
            return Decimal(value.strip())
        if isinstance(col_type, LargeBinary) and isinstance(value, dict):
            return base64.b64decode(value["$bytes"])
    except (KeyError, ValueError, TypeError, ArithmeticError) as exc:
        raise PortableError(
            f"{column.table.name}.{column.name} holds a value this version cannot read: "
            f"{value!r}"
        ) from exc
    return value


async def export_rows(conn: AsyncConnection) -> dict[str, list[dict]]:
    """Every row of every table, JSON-ready."""
    exported: dict[str, list[dict]] = {}
    for table in tables_in_load_order():
        result = await conn.execute(select(table))
        rows = [
            {col.name: encode_value(col, row[col.name]) for col in table.columns}
            for row in result.mappings()
        ]
        exported[table.name] = rows
        logger.debug("Exported %d row(s) from %s", len(rows), table.name)
    return exported


# --- decoding and validation ---------------------------------------------------


def decode_rows(
    data: dict[str, list[dict]], summary: LoadSummary
) -> dict[str, list[dict]]:
    """Decode every row for this schema.

    Columns the archive has but this schema lacks are dropped and reported:
    they come from an older archive whose columns have since been removed.
    Columns this schema has but the archive lacks are omitted, so their
    defaults apply.
    """
    unknown_tables = sorted(set(data) - set(Base.metadata.tables))
    if unknown_tables:
        raise PortableError(
            f"The archive contains tables this version does not know: {unknown_tables}. "
            "It was probably made by a newer version of Typecast."
        )

    decoded: dict[str, list[dict]] = {}
    for table in tables_in_load_order():
        rows = data.get(table.name, [])
        known = {c.name for c in table.columns}
        dropped: set[str] = set()
        out = []
        for row in rows:
            dropped.update(set(row) - known)
            out.append(
                {
                    name: decode_value(table.columns[name], value)
                    for name, value in row.items()
                    if name in known
                }
            )
        for name in sorted(dropped):
            summary.dropped_columns.append(f"{table.name}.{name}")
        decoded[table.name] = out
    if summary.dropped_columns:
        logger.warning("Archive columns not in this schema: %s", summary.dropped_columns)
    return decoded


def validate_rows(decoded: dict[str, list[dict]], dialect: str, limit: int = 20) -> list[str]:
    """Problems the target database would reject, found before writing anything.

    SQLite ignores VARCHAR lengths and stores NUL characters; Postgres refuses
    both. Checking up front means a bad row produces a readable list instead of
    a driver error halfway through a transaction.
    """
    problems: list[str] = []
    strict = dialect == "postgresql"
    for table in tables_in_load_order():
        for row in decoded.get(table.name, []):
            ident = row.get("id", "?")
            for name, value in row.items():
                column = table.columns[name]
                if isinstance(value, str) and strict:
                    if "\x00" in value:
                        problems.append(f"{table.name}.{name} (id {ident}) contains a NUL byte")
                    length = getattr(column.type, "length", None)
                    if (
                        isinstance(column.type, String)
                        and not isinstance(column.type, Enum)
                        and length
                        and len(value) > length
                    ):
                        problems.append(
                            f"{table.name}.{name} (id {ident}) is {len(value)} characters; "
                            f"the limit is {length}"
                        )
                if len(problems) >= limit:
                    return problems
    return problems


# --- loading -------------------------------------------------------------------


async def _insert_all(conn: AsyncConnection, table: Table, rows: list[dict]) -> None:
    if rows:
        await conn.execute(insert(table), rows)


async def replace_rows(
    conn: AsyncConnection,
    decoded: dict[str, list[dict]],
    summary: LoadSummary,
    can_decrypt,
) -> None:
    """Empty every table, then load the archive as-is.

    ``can_decrypt`` reports whether this install can read a secret. Secrets
    encrypted under a different SECRET_KEY are dropped rather than restored,
    because every later read would raise and break whatever feature uses them.
    """
    configs = decoded.get("app_config", [])
    kept = []
    for row in configs:
        if row.get("is_secret") and row.get("value") and not can_decrypt(row["value"]):
            summary.secrets_dropped += 1
            summary.skipped_config.append(row["key"])
            continue
        kept.append(row)
    decoded = {**decoded, "app_config": kept}
    if summary.secrets_dropped:
        logger.warning(
            "Dropping %d secret(s) encrypted with a different SECRET_KEY",
            summary.secrets_dropped,
        )

    for table in reversed(tables_in_load_order()):
        await conn.execute(delete(table))
    for table in tables_in_load_order():
        rows = decoded.get(table.name, [])
        await _insert_all(conn, table, rows)
        summary.rows[table.name] = len(rows)
    logger.info("Replaced all tables (%d rows)", summary.total_rows)


async def _existing_ids(conn: AsyncConnection, table: Table, ids: list) -> set:
    found: set = set()
    for start in range(0, len(ids), _IN_CHUNK):
        chunk = ids[start : start + _IN_CHUNK]
        result = await conn.execute(select(table.c.id).where(table.c.id.in_(chunk)))
        found.update(result.scalars().all())
    return found


def _fk_columns_to(table: Table, target: str) -> list[str]:
    return [
        col.name
        for col in table.columns
        if any(fk.column.table.name == target for fk in col.foreign_keys)
    ]


async def merge_rows(
    conn: AsyncConnection,
    decoded: dict[str, list[dict]],
    summary: LoadSummary,
    owner_id: uuid.UUID,
) -> None:
    """Add the archive's works to this install, owned by ``owner_id``.

    IDs are kept, which keeps every reference intact: foreign keys, the
    polymorphic ``codex_associations.target_id``, and upload paths such as
    ``/uploads/images/<work_id>/`` that are embedded in scene text. The price is
    that the same content cannot be imported twice, so any overlap refuses the
    whole import rather than producing half a copy.
    """
    tables = {t.name: t for t in tables_in_load_order()}

    # 1. Refuse on any overlap with content that already exists.
    clashes = {}
    for name, role in TABLE_ROLES.items():
        if role != CONTENT:
            continue
        ids = [row["id"] for row in decoded.get(name, []) if "id" in row]
        if ids:
            existing = await _existing_ids(conn, tables[name], ids)
            if existing:
                clashes[name] = len(existing)
    if clashes:
        detail = ", ".join(f"{n} {t}" for t, n in clashes.items())
        raise PortableError(
            f"This archive's content is already here ({detail}). It may have been "
            "imported before. Nothing was changed."
        )

    # 2. Profiles. Built-ins exist in every install under different IDs, so they
    # are matched by name and never inserted; references are rewritten.
    profiles = tables["profiles"]
    result = await conn.execute(
        select(profiles.c.id, profiles.c.name).where(profiles.c.is_builtin.is_(True))
    )
    builtin_here = {name: pid for pid, name in result.all()}
    archive_profiles = decoded.get("profiles", [])
    existing_profiles = await _existing_ids(
        conn, profiles, [r["id"] for r in archive_profiles]
    )
    profile_map: dict = {}
    profile_rows = []
    for row in archive_profiles:
        if row.get("is_builtin") and row.get("name") in builtin_here:
            target = builtin_here[row["name"]]
            if target != row["id"]:
                profile_map[row["id"]] = target
                summary.profiles_remapped += 1
        elif row["id"] not in existing_profiles:
            profile_rows.append(row)
    await _insert_all(conn, profiles, profile_rows)
    summary.rows["profiles"] = len(profile_rows)

    # 3. Fonts: install-wide, added only if absent.
    fonts = tables["fonts"]
    archive_fonts = decoded.get("fonts", [])
    existing_fonts = await _existing_ids(conn, fonts, [r["id"] for r in archive_fonts])
    font_rows = [r for r in archive_fonts if r["id"] not in existing_fonts]
    await _insert_all(conn, fonts, font_rows)
    summary.rows["fonts"] = len(font_rows)

    # 4. Settings: non-secret, non-Drive, and only where this install has none.
    config = tables["app_config"]
    result = await conn.execute(select(config.c.key))
    keys_here = set(result.scalars().all())
    config_rows = []
    for row in decoded.get("app_config", []):
        key = row.get("key", "")
        if row.get("is_secret") or key.startswith(_NON_PORTABLE_CONFIG_PREFIXES):
            summary.skipped_config.append(key)
            continue
        if key in keys_here:
            summary.skipped_config.append(key)
            continue
        # Let this install mint the ID; only the key is meaningful.
        config_rows.append({k: v for k, v in row.items() if k != "id"})
    await _insert_all(conn, config, config_rows)
    summary.rows["app_config"] = len(config_rows)

    # 5. Content, in dependency order, owned by the importing account.
    for table in tables_in_load_order():
        if TABLE_ROLES.get(table.name) != CONTENT:
            continue
        user_cols = _fk_columns_to(table, "users")
        profile_cols = _fk_columns_to(table, "profiles")
        rows = []
        for row in decoded.get(table.name, []):
            row = dict(row)
            for col in user_cols:
                if col in row:
                    row[col] = owner_id
            for col in profile_cols:
                if row.get(col) in profile_map:
                    row[col] = profile_map[row[col]]
            rows.append(row)
        await _insert_all(conn, table, rows)
        summary.rows[table.name] = len(rows)

    logger.info(
        "Merged %d row(s) into account %s (%d profile reference(s) remapped)",
        summary.total_rows, owner_id, summary.profiles_remapped,
    )
