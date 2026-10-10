from __future__ import annotations

import logging
import os
from collections.abc import MutableMapping
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from pydantic_settings import BaseSettings, SettingsConfigDict

from app import paths

logger = logging.getLogger(__name__)

# Absolute, and the same directory the uploads resolve to. The old default was
# relative to the working directory, so launching the server from anywhere but
# backend/ put the database somewhere the uploads were not.
_DEFAULT_DB_URL = f"sqlite+aiosqlite:///{paths.DB_PATH}"

# libpq spells TLS "sslmode"; asyncpg spells it "ssl" and raises TypeError on
# "sslmode". Every managed-Postgres console hands out a libpq connection string,
# so the wrong spelling is the default mistake rather than an unusual one.
_SSLMODE_TO_ASYNCPG = {
    "disable": "disable",
    "allow": "prefer",
    "prefer": "prefer",
    "require": "require",
    "verify-ca": "verify-ca",
    "verify-full": "verify-full",
}


def normalize_database_url(url: str) -> str:
    """Make a hand-pasted Postgres URL work with the async driver.

    Two corrections, both for connection strings copied out of a cloud console:

    * ``postgresql://`` selects psycopg2, which is synchronous and fails under
      ``create_async_engine``. Rewrite it to the asyncpg driver.
    * ``?sslmode=require`` is libpq syntax that asyncpg rejects outright. Rewrite
      it to the equivalent ``?ssl=`` value so TLS stays on rather than silently
      turning into a connection error.

    Non-Postgres URLs are returned unchanged.
    """
    split = urlsplit(url)
    if not split.scheme.startswith("postgres"):
        return url

    scheme = split.scheme
    if "+" not in scheme:
        scheme = "postgresql+asyncpg"
        logger.info("Database URL had no driver; using asyncpg")

    query = parse_qsl(split.query, keep_blank_values=True)
    if scheme.endswith("asyncpg"):
        rewritten = []
        for key, value in query:
            if key == "sslmode":
                mapped = _SSLMODE_TO_ASYNCPG.get(value.lower())
                if mapped is None:
                    logger.warning("Unrecognised sslmode=%s; leaving it in place", value)
                    rewritten.append((key, value))
                    continue
                logger.info("Rewrote sslmode=%s to ssl=%s for asyncpg", value, mapped)
                rewritten.append(("ssl", mapped))
            else:
                rewritten.append((key, value))
        query = rewritten

    return urlunsplit((scheme, split.netloc, split.path, urlencode(query), split.fragment))


def ensure_ssl_root_cert(url: str, env: MutableMapping[str, str] | None = None) -> str | None:
    """Give certificate verification something to verify against.

    Under ``verify-ca``/``verify-full`` asyncpg behaves like libpq: it trusts only
    ``sslrootcert`` from the URL, then ``PGSSLROOTCERT``, then
    ``~/.postgresql/root.crt``, and refuses to connect when none exists. It never
    falls back to the system store, so on a container with no root.crt every
    connection failed before reaching the server. Point ``PGSSLROOTCERT`` at
    certifi's Mozilla bundle, which carries the public roots managed Postgres
    services chain to. A CA file the deployer supplies either way wins.

    Returns the path set, or None when nothing needed setting.
    """
    env = os.environ if env is None else env
    split = urlsplit(url)
    if not split.scheme.startswith("postgres"):
        return None
    query = dict(parse_qsl(split.query, keep_blank_values=True))
    mode = (query.get("ssl") or query.get("sslmode") or "").lower()
    if mode not in ("verify-ca", "verify-full"):
        return None
    if query.get("sslrootcert") or env.get("PGSSLROOTCERT"):
        logger.debug("Postgres CA file supplied by the deployer; leaving it alone")
        return None
    import certifi

    bundle = certifi.where()
    env["PGSSLROOTCERT"] = bundle
    logger.info("ssl=%s with no root certificate configured; trusting %s", mode, bundle)
    return bundle


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    DATABASE_URL: str = _DEFAULT_DB_URL
    EXPORT_PROFILES_DIR: str = "./profiles"
    AI_PROVIDER: str = "anthropic"
    AI_API_KEY: str | None = None
    AI_MODEL: str | None = None
    SECRET_KEY: str = "change-me-in-production"

    @property
    def database_url(self) -> str:
        """``DATABASE_URL`` corrected for the async driver. Use this to connect."""
        return normalize_database_url(self.DATABASE_URL)

    @property
    def is_postgres(self) -> bool:
        return self.database_url.startswith("postgres")


settings = Settings()
# Before any engine exists, so the app engine, the migration engine, and the
# Alembic CLI all connect with it.
ensure_ssl_root_cert(settings.database_url)
