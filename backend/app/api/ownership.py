"""Per-resource authorization: does the signed-in account own this?

Every resource reachable by ID resolves to an owning account by walking up to
a work, series, conversation, or codex entry. A resource the caller does not
own answers 404, the same as one that does not exist, so IDs cannot be probed
for existence.

Administrators get no exception. They manage accounts; they do not read other
people's manuscripts.

Two entry points:

* ``enforce_path_ownership`` is attached to every router in app/main.py. It
  checks each resource ID in the matched route's path, so a new route is
  covered the moment it is added. It only queries owner columns, so it puts no
  objects in the session and cannot change what a handler's own eager-loading
  query returns.
* ``require_owned`` for IDs that arrive in a request body or from an AI tool
  call, where there is no path parameter.

``tests/test_authorization.py`` fails if a path parameter has no ownership rule,
and probes every ID-taking route as a second account.
"""

from __future__ import annotations

import logging
import uuid
from collections.abc import Iterable

from fastapi import Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.db.engine import get_db
from app.models.chapter import Chapter
from app.models.codex import CodexEntry
from app.models.codex_image import CodexImage
from app.models.comment import Comment
from app.models.conversation import Conversation
from app.models.image import Image
from app.models.scene import Scene
from app.models.section import Section
from app.models.series import Series
from app.models.user import User
from app.models.work import Work

logger = logging.getLogger(__name__)


# Each kind maps to a query for the owning user_id of one row. Every chain ends
# at a column that holds an account ID.
def _owner_query(kind: str, resource_id: uuid.UUID):
    if kind == "work":
        return select(Work.user_id).where(Work.id == resource_id)
    if kind == "series":
        return select(Series.user_id).where(Series.id == resource_id)
    if kind == "conversation":
        return select(Conversation.user_id).where(Conversation.id == resource_id)
    if kind == "codex_entry":
        return select(CodexEntry.user_id).where(CodexEntry.id == resource_id)
    if kind == "chapter":
        return (
            select(Work.user_id)
            .join(Chapter, Chapter.work_id == Work.id)
            .where(Chapter.id == resource_id)
        )
    if kind == "scene":
        return (
            select(Work.user_id)
            .join(Chapter, Chapter.work_id == Work.id)
            .join(Scene, Scene.chapter_id == Chapter.id)
            .where(Scene.id == resource_id)
        )
    if kind == "comment":
        return (
            select(Work.user_id)
            .join(Chapter, Chapter.work_id == Work.id)
            .join(Scene, Scene.chapter_id == Chapter.id)
            .join(Comment, Comment.scene_id == Scene.id)
            .where(Comment.id == resource_id)
        )
    if kind == "section":
        return (
            select(Work.user_id)
            .join(Section, Section.work_id == Work.id)
            .where(Section.id == resource_id)
        )
    if kind == "image":
        return select(Work.user_id).join(Image, Image.work_id == Work.id).where(
            Image.id == resource_id
        )
    if kind == "codex_image":
        return (
            select(CodexEntry.user_id)
            .join(CodexImage, CodexImage.codex_entry_id == CodexEntry.id)
            .where(CodexImage.id == resource_id)
        )
    raise ValueError(f"unknown resource kind {kind!r}")


_LABELS = {
    "work": "Work",
    "series": "Series",
    "conversation": "Conversation",
    "codex_entry": "Codex entry",
    "chapter": "Chapter",
    "scene": "Scene",
    "comment": "Comment",
    "section": "Section",
    "image": "Image",
    "codex_image": "Codex image",
}


async def owns(db: AsyncSession, user: User, kind: str, resource_id: uuid.UUID) -> bool:
    """True when the row exists and belongs to ``user``."""
    owner = (await db.execute(_owner_query(kind, resource_id))).scalar_one_or_none()
    return owner is not None and owner == user.id


async def require_owned(
    db: AsyncSession, user: User, kind: str, resource_ids: uuid.UUID | Iterable[uuid.UUID] | None
) -> None:
    """Raise 404 unless every given ID exists and belongs to ``user``.

    Accepts a single ID, an iterable, or None (nothing to check). For IDs taken
    from a request body.
    """
    if resource_ids is None:
        return
    ids = [resource_ids] if isinstance(resource_ids, uuid.UUID) else list(resource_ids)
    for resource_id in ids:
        if not await owns(db, user, kind, resource_id):
            logger.warning(
                "Denied %s %s to %s (not found or not theirs)", kind, resource_id, user.email
            )
            raise HTTPException(status_code=404, detail=f"{_LABELS[kind]} not found")


# --- the router-level dependency ---------------------------------------------------

# Path parameter -> resource kind. Parameters naming install-wide resources
# (fonts, profiles) or accounts (administrator routes) are deliberately absent.
_KIND_BY_PARAM = {
    "work_id": "work",
    "series_id": "series",
    "chapter_id": "chapter",
    "scene_id": "scene",
    "comment_id": "comment",
    "section_id": "section",
    "conversation_id": "conversation",
    "entry_id": "codex_entry",
}
NOT_OWNED_PARAMS = frozenset({"font_id", "profile_id", "user_id"})


def ownership_kind(route_path: str, param: str) -> str | None:
    """The resource kind a path parameter names, given the route's template.

    ``image_id`` is ambiguous on its own: under /api/codex it is a codex
    image, elsewhere a work's gallery image.
    """
    if param == "image_id":
        return "codex_image" if route_path.startswith("/api/codex/") else "image"
    return _KIND_BY_PARAM.get(param)


async def enforce_path_ownership(
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    """Refuse the request unless the caller owns every resource in its path."""
    route = request.scope.get("route")
    template = getattr(route, "path", request.url.path)
    for param, raw in request.path_params.items():
        if param in NOT_OWNED_PARAMS:
            continue
        kind = ownership_kind(template, param)
        if kind is None:
            # Fail closed: an unclassified ID is refused, not waved through.
            logger.error("No ownership rule for {%s} on %s", param, template)
            raise HTTPException(status_code=404, detail="Not found")
        try:
            resource_id = uuid.UUID(str(raw))
        except ValueError:
            raise HTTPException(status_code=404, detail=f"{_LABELS[kind]} not found") from None
        await require_owned(db, user, kind, resource_id)
