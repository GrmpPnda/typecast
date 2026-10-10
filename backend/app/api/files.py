"""Serving uploaded files to the accounts they belong to.

Uploads used to be a public StaticFiles mount: anyone with a URL could fetch the
file, and only the random IDs in the paths kept them private. Behind an
authenticating proxy that was covered at the edge; with sign-in moving into the
app, it has to be covered here.

Signing in is required (the router's dependency; browsers authenticate with the
uploads cookie, see deps.py), and then the path decides who may read it:

* ``images/<work_id>/...``: the work's owner
* ``codex/<entry_id>/...``: the codex entry's owner
* ``covers/<file>``: the owner of the work or series using it as its cover
* ``fonts/<file>``: any signed-in account, since fonts are install-wide

Anything else, including a file that is not there, is 404, so a path cannot be
used to learn whether a file exists.
"""

from __future__ import annotations

import logging
import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app import paths
from app.api.deps import get_current_user
from app.api.ownership import owns
from app.db.engine import get_db
from app.models.series import Series
from app.models.user import User
from app.models.work import Work

logger = logging.getLogger(__name__)
router = APIRouter()

UPLOAD_DIR = paths.UPLOAD_DIR

_NOT_FOUND = HTTPException(status_code=404, detail="Not found")


def _resolve(path: str) -> Path:
    """The file under UPLOAD_DIR that ``path`` names, or 404."""
    root = UPLOAD_DIR.resolve()
    target = (root / path).resolve()
    if not target.is_relative_to(root) or not target.is_file():
        raise _NOT_FOUND
    return target


async def _may_read(db: AsyncSession, user: User, parts: list[str], url_path: str) -> bool:
    folder = parts[0]
    if folder == "fonts" and len(parts) == 2:
        return True
    if folder in ("images", "codex") and len(parts) == 3:
        try:
            owner_id = uuid.UUID(parts[1])
        except ValueError:
            return False
        kind = "work" if folder == "images" else "codex_entry"
        return await owns(db, user, kind, owner_id)
    if folder == "covers" and len(parts) == 2:
        for model in (Work, Series):
            found = await db.scalar(
                select(model.id).where(
                    model.cover_image_path == url_path, model.user_id == user.id
                ).limit(1)
            )
            if found is not None:
                return True
    return False


@router.api_route("/{path:path}", methods=["GET", "HEAD"])
async def read_upload(
    path: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    parts = [p for p in path.split("/") if p]
    if not parts:
        raise _NOT_FOUND
    url_path = "/uploads/" + "/".join(parts)
    if not await _may_read(db, user, parts, url_path):
        logger.info("Upload %s refused for %s", url_path, user.email)
        raise _NOT_FOUND
    target = _resolve("/".join(parts))
    logger.debug("Serving upload %s to %s", url_path, user.email)
    # Private: a shared cache must never hand one account's file to another.
    return FileResponse(target, headers={"Cache-Control": "private, max-age=3600"})
