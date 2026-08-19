"""Filesystem locations for the database and uploads.

Single source of truth for ``TYPECAST_DATA_DIR``. Every module that reads or
writes an upload must resolve through here: ``app/main.py`` mounts the static
``/uploads`` route from this location, so a module that computes its own
backend-relative path writes files the server will never serve.
"""

from __future__ import annotations

import logging
import os
from collections.abc import Mapping
from pathlib import Path

logger = logging.getLogger(__name__)

# backend/, i.e. the parent of the app package. The default data dir, kept for
# the common case where TYPECAST_DATA_DIR is unset.
BACKEND_DIR = Path(__file__).resolve().parent.parent


def resolve_data_dir(env: Mapping[str, str] | None = None) -> Path:
    """Where the database and uploads live.

    Takes ``env`` so callers can test alternate configurations without
    reimporting the module: a reload rebinds module-level classes, which breaks
    ``except`` clauses in code that already imported them.
    """
    source = os.environ if env is None else env
    configured = source.get("TYPECAST_DATA_DIR")
    if configured:
        logger.debug("Data dir from TYPECAST_DATA_DIR: %s", configured)
        return Path(configured)
    return BACKEND_DIR


def resolve_upload_dir(env: Mapping[str, str] | None = None) -> Path:
    """The uploads root, honouring a custom data dir."""
    return resolve_data_dir(env) / "uploads"


DATA_DIR = resolve_data_dir()
DB_PATH = DATA_DIR / "typecast.db"
UPLOAD_DIR = resolve_upload_dir()
