"""Guards for running on Postgres instead of SQLite.

The app was SQLite-only in ways that were invisible until something tried to
connect to Postgres: a ``PRAGMA`` sent on every connection, column existence
probed with ``PRAGMA table_info``, ``BOOLEAN DEFAULT 0``, and ``is_builtin = 1``.
Those are gone; these tests keep them from coming back and keep the Alembic
baseline honest.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

from app.config import normalize_database_url
from app.db.base import Base

BACKEND_DIR = Path(__file__).resolve().parent.parent
APP_DIR = BACKEND_DIR / "app"
VERSIONS_DIR = BACKEND_DIR / "alembic" / "versions"


# --- connection URL handling ----------------------------------------------


@pytest.mark.parametrize(
    ("given", "expected"),
    [
        # The form every managed-Postgres console hands out.
        (
            "postgresql://u:p@h:5432/db?sslmode=require",
            "postgresql+asyncpg://u:p@h:5432/db?ssl=require",
        ),
        ("postgresql+asyncpg://u:p@h/db?sslmode=verify-full",
         "postgresql+asyncpg://u:p@h/db?ssl=verify-full"),
        # "allow" has no asyncpg equivalent; "prefer" is the closest.
        ("postgresql+asyncpg://u:p@h/db?sslmode=allow",
         "postgresql+asyncpg://u:p@h/db?ssl=prefer"),
        # Already correct, so left alone.
        ("postgresql+asyncpg://u:p@h/db?ssl=require",
         "postgresql+asyncpg://u:p@h/db?ssl=require"),
        # Bare postgres:// would select the synchronous psycopg2 driver.
        ("postgres://u:p@h/db", "postgresql+asyncpg://u:p@h/db"),
        # Non-Postgres URLs must pass through untouched.
        ("sqlite+aiosqlite:////data/typecast.db", "sqlite+aiosqlite:////data/typecast.db"),
    ],
)
def test_database_url_is_corrected_for_the_async_driver(given, expected):
    assert normalize_database_url(given) == expected


def test_tls_is_never_silently_dropped():
    """A mangled sslmode must not become a plaintext connection."""
    out = normalize_database_url("postgresql+asyncpg://u:p@h/db?sslmode=nonsense")
    assert "sslmode=nonsense" in out  # left for the driver to reject loudly
    assert "ssl=disable" not in out


def test_password_special_characters_survive_normalization():
    url = "postgresql://u:p%40ss%2Fword@h:5432/db?sslmode=require"
    assert "p%40ss%2Fword" in normalize_database_url(url)


# --- no SQLite-only SQL in the app ----------------------------------------


def _string_constants(tree: ast.AST) -> list[str]:
    return [
        node.value
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant) and isinstance(node.value, str)
    ]


# A module may issue SQLite-only SQL as long as it checks the dialect first.
_DIALECT_GUARDS = ("dialect.name", "is_postgres", "_require_sqlite")


def test_sqlite_only_sql_always_sits_behind_a_dialect_check():
    """PRAGMA and boolean-as-integer comparisons fail outright on Postgres.

    Both legitimate uses are guarded: app/db/engine.py checks
    ``engine.dialect.name``, and app/services/backup.py calls
    ``_require_sqlite()`` because a file-copy backup cannot work on a server
    database at all.
    """
    offenders = []
    for source in sorted(APP_DIR.rglob("*.py")):
        text = source.read_text()
        tree = ast.parse(text)
        hits = [
            value
            for value in _string_constants(tree)
            if "PRAGMA " in value.upper()
            or "IS_BUILTIN = 1" in value.upper()
            or "BOOLEAN DEFAULT 0" in value.upper()
        ]
        if not hits:
            continue
        if not any(guard in text for guard in _DIALECT_GUARDS):
            rel = source.relative_to(BACKEND_DIR)
            offenders.append(f"{rel}: {hits[0][:60]}")
    assert offenders == [], (
        f"SQLite-only SQL with no dialect guard: {offenders}. "
        f"Guard it with one of {_DIALECT_GUARDS}."
    )


def _legacy_archive() -> bytes:
    import io
    import zipfile

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("typecast.db", b"SQLite format 3\x00")
    return buf.getvalue()


async def test_legacy_restore_refuses_to_run_on_postgres(monkeypatch):
    """A version 1 archive is a SQLite file; Postgres cannot load it.

    Version 2 archives work on both, so this is now the only backup operation
    that is dialect-specific.
    """
    from app.services import backup

    monkeypatch.setattr(
        type(backup.settings), "is_postgres", property(lambda self: True)
    )
    with pytest.raises(backup.BackupUnsupportedError, match="only a SQLite install"):
        await backup.restore_backup_archive(_legacy_archive())


async def test_legacy_restore_explains_itself_over_http_on_postgres(client, monkeypatch):
    """The reason must reach the user as a 501, not a generic 500.

    The restore endpoints once let this error escape to the global handler.
    Found by running the container against a real Postgres.
    """
    from app.services import backup

    monkeypatch.setattr(
        type(backup.settings), "is_postgres", property(lambda self: True)
    )
    resp = await client.post(
        "/api/backup/restore",
        files={"file": ("old.zip", _legacy_archive(), "application/zip")},
    )
    assert resp.status_code == 501
    assert "only a SQLite install" in resp.json()["detail"]


def test_every_backup_entry_point_maps_the_unsupported_error():
    """Guards the two Drive call sites the test above cannot reach.

    Any call to build_backup_archive or restore_backup_archive must sit inside a
    try block, or its error becomes a 500 with no explanation.
    """
    offenders = []
    for name in ("backup.py", "gdrive.py"):
        source = APP_DIR / "api" / name
        tree = ast.parse(source.read_text())
        for func in [n for n in ast.walk(tree) if isinstance(n, ast.AsyncFunctionDef)]:
            guarded = {
                id(call)
                for handler in [n for n in ast.walk(func) if isinstance(n, ast.Try)]
                for call in ast.walk(handler)
                if isinstance(call, ast.Call)
            }
            for call in ast.walk(func):
                if (
                    isinstance(call, ast.Call)
                    and isinstance(call.func, ast.Name)
                    and call.func.id
                    in ("build_backup_archive", "restore_backup_archive", "import_backup_archive")
                    and id(call) not in guarded
                ):
                    offenders.append(f"{name}:{func.name} calls {call.func.id} unguarded")
    assert offenders == [], offenders


def test_the_sqlite_pragma_is_gated_on_the_dialect():
    """It used to run on every connect, so Postgres failed on connection."""
    text = (APP_DIR / "db" / "engine.py").read_text()
    tree = ast.parse(text)
    func = next(
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef) and node.name == "_set_sqlite_pragma"
    )
    guards = [n for n in ast.walk(func) if isinstance(n, ast.If)]
    assert guards, "_set_sqlite_pragma must bail out on a non-SQLite dialect"
    assert "dialect" in ast.unparse(guards[0].test)


# --- Alembic baseline -----------------------------------------------------


def _migration_tables() -> set[str]:
    tables: set[str] = set()
    for revision in VERSIONS_DIR.glob("*.py"):
        tree = ast.parse(revision.read_text())
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and node.func.attr == "create_table"
                and node.args
                and isinstance(node.args[0], ast.Constant)
            ):
                tables.add(node.args[0].value)
    return tables


def test_migrations_cover_every_model_table():
    """Postgres schema comes only from Alembic, so a model missing from the
    migrations is a table that never gets created on the deployment."""
    missing = set(Base.metadata.tables) - _migration_tables()
    assert missing == set(), (
        f"these tables exist in the models but no migration creates them: {sorted(missing)}. "
        "Run: alembic revision --autogenerate"
    )


def test_migrations_declare_no_dialect_specific_types():
    """Migrations must apply to SQLite and Postgres alike.

    Dialect-specific SQL is allowed only in a migration that branches on the
    dialect, which is sometimes the only correct option: Alembic silently drops
    an inline foreign key from ADD COLUMN on SQLite, so the codex-owner
    migration writes that statement out for SQLite.
    """
    offenders = []
    for revision in VERSIONS_DIR.glob("*.py"):
        text = revision.read_text()
        if "dialect.name" in text:
            continue
        for marker in ("postgresql.", "sqlite.", "JSONB", "CHAR(32)", "CHAR(36)"):
            if marker in text:
                offenders.append(f"{revision.name}: {marker}")
    assert offenders == [], f"dialect-specific types in migrations: {offenders}"


# --- model registration ---------------------------------------------------


def test_importing_app_models_registers_every_table():
    """Alembic autogenerate and the test harness only import app.models.

    A model omitted from app/models/__init__.py is invisible to both even though
    the app still works, because importing the API layer registers it as a side
    effect. That is how the comments table came to be missing from the first
    generated baseline.
    """
    import importlib

    import app.models

    modules = {
        p.stem for p in (APP_DIR / "models").glob("*.py") if p.stem != "__init__"
    }
    registered = set(Base.metadata.tables)

    unregistered = []
    for name in sorted(modules):
        module = importlib.import_module(f"app.models.{name}")
        for attr in vars(module).values():
            table = getattr(attr, "__tablename__", None)
            if table and getattr(attr, "__module__", "") == module.__name__:
                if table not in registered:
                    unregistered.append(f"{name}.{attr.__name__} -> {table}")
                if attr.__name__ not in app.models.__all__:
                    unregistered.append(f"{attr.__name__} missing from app.models.__all__")

    assert unregistered == [], f"models not exported from app.models: {unregistered}"
