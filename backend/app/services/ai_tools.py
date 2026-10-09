from __future__ import annotations

import re
import logging
import uuid
from contextvars import ContextVar
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.chapter import Chapter
from app.models.codex import CodexEntry
from app.models.codex_association import CodexAssociation
from app.models.scene import Scene
from app.models.series import Series
from app.models.work import Work

logger = logging.getLogger(__name__)

TOOL_DEFINITIONS = [
    {
        "name": "create_series",
        "description": "Create a new book series. Use when the user wants to start a new series.",
        "input_schema": {
            "type": "object",
            "properties": {
                "title": {"type": "string", "description": "Series title"},
                "description": {
                    "type": "string",
                    "description": "Series description/summary",
                },
            },
            "required": ["title"],
        },
    },
    {
        "name": "create_work",
        "description": (
            "Create a new book/work. Use when the user wants to start writing a new book. "
            "Can optionally be added to a series."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "title": {"type": "string", "description": "Book title"},
                "author": {"type": "string", "description": "Author name"},
                "description": {"type": "string", "description": "Book description/premise"},
                "blurb": {"type": "string", "description": "Short promotional blurb"},
                "genre": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Genre tags",
                },
                "series_id": {
                    "type": "string",
                    "description": "UUID of series to add this work to",
                },
            },
            "required": ["title", "author"],
        },
    },
    {
        "name": "create_chapter",
        "description": (
            "Create a new chapter in a work. Use when the user wants to add a chapter. "
            "The chapter will be created with a single scene containing the provided content."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "work_id": {"type": "string", "description": "UUID of the work"},
                "title": {"type": "string", "description": "Chapter title"},
                "synopsis": {"type": "string", "description": "Chapter synopsis/outline"},
                "content": {
                    "type": "string",
                    "description": "Chapter content (markdown). Will be placed in the first scene.",
                },
            },
            "required": ["work_id", "title"],
        },
    },
    {
        "name": "write_scene",
        "description": (
            "Write or update a scene's content. Use when the user asks you to write, "
            "continue, or rewrite a scene. The prose you write MUST match the author's "
            "existing style — study the surrounding scenes in the work context for "
            "sentence structure, vocabulary, dialogue style, and narrative distance."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "scene_id": {"type": "string", "description": "UUID of the scene to update"},
                "content": {
                    "type": "string",
                    "description": "The scene content (markdown format)",
                },
            },
            "required": ["scene_id", "content"],
        },
    },
    {
        "name": "create_codex_entry",
        "description": (
            "Create a codex entry (character, location, event, item, species, timeline, or custom). "
            "Use when the user wants to add world-building information."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "Entry name"},
                "entry_type": {
                    "type": "string",
                    "enum": ["character", "location", "event", "species", "item", "timeline", "custom"],
                    "description": "Type of codex entry",
                },
                "description": {"type": "string", "description": "Short description"},
                "content": {"type": "string", "description": "Detailed content (markdown)"},
                "work_id": {
                    "type": "string",
                    "description": "UUID of the work to associate with",
                },
            },
            "required": ["name", "entry_type"],
        },
    },
    {
        "name": "bulk_create_codex",
        "description": (
            "Create multiple codex entries at once for a work. Use this when the user asks you to "
            "generate, build, or populate a full codex from a work. You must analyze the work's "
            "content and extract all characters, locations, events, items, species, etc. "
            "Create thorough, detailed entries for each. This is preferred over calling "
            "create_codex_entry multiple times."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "work_id": {"type": "string", "description": "UUID of the work"},
                "entries": {
                    "type": "array",
                    "description": "Array of codex entries to create",
                    "items": {
                        "type": "object",
                        "properties": {
                            "name": {"type": "string", "description": "Entry name"},
                            "entry_type": {
                                "type": "string",
                                "enum": [
                                    "character", "location", "event",
                                    "species", "item", "timeline", "custom",
                                ],
                            },
                            "description": {
                                "type": "string",
                                "description": "Short one-line description",
                            },
                            "content": {
                                "type": "string",
                                "description": "Detailed content in markdown",
                            },
                        },
                        "required": ["name", "entry_type"],
                    },
                },
            },
            "required": ["work_id", "entries"],
        },
    },
    {
        "name": "update_codex_entry",
        "description": "Update an existing codex entry's content or description.",
        "input_schema": {
            "type": "object",
            "properties": {
                "entry_id": {"type": "string", "description": "UUID of the codex entry"},
                "name": {"type": "string", "description": "Updated name"},
                "description": {"type": "string", "description": "Updated description"},
                "content": {"type": "string", "description": "Updated content (markdown)"},
            },
            "required": ["entry_id"],
        },
    },
    {
        "name": "summarize_work",
        "description": (
            "Read a work's full content and produce a summary. "
            "Use when the user asks for a summary of a book/work."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "work_id": {"type": "string", "description": "UUID of the work to summarize"},
            },
            "required": ["work_id"],
        },
    },
    {
        "name": "list_works",
        "description": "List all works, optionally filtered by series. Use to find work IDs.",
        "input_schema": {
            "type": "object",
            "properties": {
                "series_id": {
                    "type": "string",
                    "description": "UUID of series to filter by (optional)",
                },
            },
            "required": [],
        },
    },
    {
        "name": "list_series",
        "description": "List all series. Use to find series IDs.",
        "input_schema": {
            "type": "object",
            "properties": {},
            "required": [],
        },
    },
    {
        "name": "list_chapters",
        "description": "List all chapters in a work. Use to find chapter/scene IDs.",
        "input_schema": {
            "type": "object",
            "properties": {
                "work_id": {"type": "string", "description": "UUID of the work"},
            },
            "required": ["work_id"],
        },
    },
    {
        "name": "list_codex_entries",
        "description": "List codex entries, optionally filtered by work. Use to find entry IDs.",
        "input_schema": {
            "type": "object",
            "properties": {
                "work_id": {
                    "type": "string",
                    "description": "Filter by work UUID (optional)",
                },
            },
            "required": [],
        },
    },
    {
        "name": "generate_image",
        "description": (
            "Generate an AI image and save it to a work's image gallery or a codex entry. "
            "Use when the user asks to create, generate, or illustrate an image. "
            "Compose a detailed visual description as the prompt — include style, composition, "
            "lighting, character appearances, and setting details. "
            "For character images, always reference their physical description from the codex. "
            "IMPORTANT: When generating images of characters or locations that have codex entries "
            "with primary images, ALWAYS include their codex entry IDs in reference_codex_ids. "
            "This passes their reference images to the image model to maintain visual consistency. "
            "Even if you cannot see the reference image yourself, the image generator will use it."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "prompt": {
                    "type": "string",
                    "description": (
                        "Detailed visual description for the image. Be specific about style, "
                        "composition, lighting, colors, character appearances, setting, mood. "
                        "The more detailed the better."
                    ),
                },
                "negative_prompt": {
                    "type": "string",
                    "description": "What to avoid in the image (e.g. 'blurry, low quality, text')",
                },
                "work_id": {
                    "type": "string",
                    "description": (
                        "UUID of the work to save the image to (work gallery). "
                        "Required if no codex_entry_id."
                    ),
                },
                "codex_entry_id": {
                    "type": "string",
                    "description": "UUID of the codex entry to save the image to. Required if no work_id or series_id.",
                },
                "series_id": {
                    "type": "string",
                    "description": (
                        "UUID of the series to save the image as banner/cover. "
                        "Use when the user asks to generate a series banner image."
                    ),
                },
                "alt_text": {
                    "type": "string",
                    "description": "Alt text describing the image for accessibility.",
                },
                "width": {
                    "type": "integer",
                    "description": "Image width in pixels. Default 1024. Common: 1024, 1280, 1792.",
                },
                "height": {
                    "type": "integer",
                    "description": "Image height in pixels. Default 1024. Common: 1024, 1280, 1792.",
                },
                "reference_codex_ids": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": (
                        "UUIDs of codex entries whose primary images should be used as visual "
                        "references for the generation. Use this when you need to maintain a "
                        "character's exact facial likeness or match a location's appearance. "
                        "The primary image from each entry will be passed to the image model."
                    ),
                },
            },
            "required": ["prompt"],
        },
    },
    {
        "name": "review_scene",
        "description": (
            "Review a single scene and leave actionable inline comments. "
            "Be selective — only flag things that genuinely weaken the writing. "
            "Aim for 3-5 comments max; fewer is fine for strong scenes. "
            "When suggesting text changes, include a 'suggestion' field with the "
            "exact replacement text for the anchor_text span."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "scene_id": {
                    "type": "string",
                    "description": "UUID of the scene to review",
                },
                "comments": {
                    "type": "array",
                    "description": "Actionable comments — only for genuine issues worth fixing",
                    "items": {
                        "type": "object",
                        "properties": {
                            "anchor_text": {
                                "type": "string",
                                "description": (
                                    "Exact verbatim substring from the scene content. "
                                    "Do NOT include markdown formatting characters "
                                    "(*, _, **, __) — use only the plain text."
                                ),
                            },
                            "content": {
                                "type": "string",
                                "description": (
                                    "The issue and a concrete suggestion to fix it."
                                ),
                            },
                            "suggestion": {
                                "type": "string",
                                "description": (
                                    "The exact replacement text for the anchor_text. "
                                    "Include this when recommending a specific text change. "
                                    "Omit for structural or high-level feedback."
                                ),
                            },
                        },
                        "required": ["anchor_text", "content"],
                    },
                },
            },
            "required": ["scene_id", "comments"],
        },
    },
    {
        "name": "review_chapter",
        "description": (
            "Review an entire chapter with actionable inline comments across all scenes. "
            "Be selective — focus on the highest-impact issues. "
            "Aim for 3-5 comments per scene max; strong scenes can have fewer or none. "
            "Call this ONCE for the whole chapter. "
            "When suggesting text changes, include a 'suggestion' field with the "
            "exact replacement text for the anchor_text span."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "chapter_id": {
                    "type": "string",
                    "description": "UUID of the chapter to review",
                },
                "scene_comments": {
                    "type": "array",
                    "description": "Comments grouped by scene",
                    "items": {
                        "type": "object",
                        "properties": {
                            "scene_id": {
                                "type": "string",
                                "description": "UUID of the scene",
                            },
                            "comments": {
                                "type": "array",
                                "items": {
                                    "type": "object",
                                    "properties": {
                                        "anchor_text": {
                                            "type": "string",
                                            "description": (
                                                "Exact verbatim substring from the scene content. "
                                                "Do NOT include markdown formatting characters "
                                                "(*, _, **, __) — use only the plain text."
                                            ),
                                        },
                                        "content": {
                                            "type": "string",
                                            "description": "Review feedback",
                                        },
                                        "suggestion": {
                                            "type": "string",
                                            "description": (
                                                "The exact replacement text for the anchor_text. "
                                                "Include this when recommending a specific text change. "
                                                "Omit for structural or high-level feedback."
                                            ),
                                        },
                                    },
                                    "required": ["anchor_text", "content"],
                                },
                            },
                        },
                        "required": ["scene_id", "comments"],
                    },
                },
            },
            "required": ["chapter_id", "scene_comments"],
        },
    },
]


# The account the current tool call acts for. Set by execute_tool for the
# duration of one call; the handlers read it through _owner_id().
_acting_user: ContextVar[uuid.UUID | None] = ContextVar("_acting_user", default=None)

# Input keys that name a resource, and the kind each one names. The model picks
# these IDs, so it could be talked into naming someone else's work; every one
# is checked before the tool runs, however deeply it is nested.
_ID_KEYS = {
    "work_id": "work",
    "series_id": "series",
    "chapter_id": "chapter",
    "scene_id": "scene",
    "entry_id": "codex_entry",
    "codex_entry_id": "codex_entry",
    "reference_codex_ids": "codex_entry",
}


def _owner_id() -> uuid.UUID:
    owner = _acting_user.get()
    if owner is None:
        raise RuntimeError("AI tool ran without an acting account")
    return owner


def _ids_in(value: Any):
    """Yield (kind, id) for every resource ID anywhere in a tool input."""
    if isinstance(value, dict):
        for key, item in value.items():
            kind = _ID_KEYS.get(key)
            if kind is not None and item:
                for raw in item if isinstance(item, list) else [item]:
                    yield kind, raw
            else:
                yield from _ids_in(item)
    elif isinstance(value, list):
        for item in value:
            yield from _ids_in(item)


async def _check_tool_ids(db: AsyncSession, user, tool_input: dict[str, Any]) -> str | None:
    """An error message if the input names anything the user does not own."""
    from app.api.ownership import owns

    for kind, raw in _ids_in(tool_input):
        try:
            resource_id = uuid.UUID(str(raw))
        except ValueError:
            return f"Invalid {kind} id: {raw}"
        if not await owns(db, user, kind, resource_id):
            logger.warning("AI tool denied %s %s for %s", kind, resource_id, user.email)
            # Worded as absence, so the model cannot use errors to probe IDs.
            return f"No {kind.replace('_', ' ')} with id {resource_id} exists"
    return None


async def execute_tool(
    db: AsyncSession,
    tool_name: str,
    tool_input: dict[str, Any],
    user,
) -> dict[str, Any]:
    handler = _HANDLERS.get(tool_name)
    if not handler:
        return {"error": f"Unknown tool: {tool_name}"}
    denied = await _check_tool_ids(db, user, tool_input)
    if denied:
        return {"error": denied}
    token = _acting_user.set(user.id)
    try:
        return await handler(db, tool_input)
    except ValueError as exc:
        return {"error": f"Invalid input: {exc}"}
    except Exception as exc:
        return {"error": f"Tool failed: {type(exc).__name__}: {exc}"}
    finally:
        _acting_user.reset(token)


async def _create_series(db: AsyncSession, inp: dict) -> dict:
    series = Series(
        title=inp["title"], description=inp.get("description", ""), user_id=_owner_id()
    )
    db.add(series)
    await db.commit()
    await db.refresh(series)
    return {"id": str(series.id), "title": series.title, "action": "created_series"}


async def _create_work(db: AsyncSession, inp: dict) -> dict:
    kwargs: dict[str, Any] = {
        "title": inp["title"],
        "author": inp["author"],
        "description": inp.get("description", ""),
        "blurb": inp.get("blurb", ""),
        "genre": inp.get("genre", []),
        "user_id": _owner_id(),
    }
    if inp.get("series_id"):
        kwargs["series_id"] = uuid.UUID(inp["series_id"])
    work = Work(**kwargs)
    db.add(work)
    await db.commit()
    await db.refresh(work)
    return {"id": str(work.id), "title": work.title, "action": "created_work"}


def _classify_title(title: str | None) -> str:
    _FRONT = {
        "half title", "title page", "copyright", "dedication", "epigraph",
        "table of contents", "foreword", "preface", "acknowledgments",
        "acknowledgements", "introduction", "prologue",
    }
    _BACK = {
        "epilogue", "afterword", "appendix", "glossary", "bibliography",
        "about the author", "also by", "colophon", "index",
    }
    t = (title or "").lower().strip()
    if t in _FRONT:
        return "front"
    if t in _BACK:
        return "back"
    return "body"


async def _create_chapter(db: AsyncSession, inp: dict) -> dict:
    work_id = uuid.UUID(inp["work_id"])
    result = await db.execute(
        select(Chapter).where(Chapter.work_id == work_id)
    )
    existing = sorted(result.scalars().all(), key=lambda c: c.sort_order)
    next_num = max((c.number or 0 for c in existing), default=0) + 1

    classification = _classify_title(inp["title"])
    if classification == "front":
        first_body = next(
            (c for c in existing if _classify_title(c.title) == "body"), None
        )
        insert_at = first_body.sort_order if first_body else (
            (existing[-1].sort_order + 1) if existing else 0
        )
    elif classification == "back":
        insert_at = (existing[-1].sort_order + 1) if existing else 0
    else:
        first_back = next(
            (c for c in existing if _classify_title(c.title) == "back"), None
        )
        insert_at = first_back.sort_order if first_back else (
            (existing[-1].sort_order + 1) if existing else 0
        )

    for ch in existing:
        if ch.sort_order >= insert_at:
            ch.sort_order += 1

    chapter = Chapter(
        work_id=work_id,
        title=inp["title"],
        number=next_num,
        sort_order=insert_at,
        synopsis=inp.get("synopsis", ""),
    )
    db.add(chapter)
    await db.flush()
    await db.refresh(chapter)

    content = inp.get("content", "")
    word_count = len(content.split()) if content else 0
    scene = Scene(
        chapter_id=chapter.id,
        sort_order=0,
        content=content,
        word_count=word_count,
    )
    db.add(scene)
    await db.commit()
    await db.refresh(chapter)
    await db.refresh(scene)

    return {
        "chapter_id": str(chapter.id),
        "scene_id": str(scene.id),
        "title": chapter.title,
        "number": chapter.number,
        "action": "created_chapter",
    }


async def _write_scene(db: AsyncSession, inp: dict) -> dict:
    scene_id = uuid.UUID(inp["scene_id"])
    result = await db.execute(select(Scene).where(Scene.id == scene_id))
    scene = result.scalar_one_or_none()
    if not scene:
        return {"error": "Scene not found"}

    had_content = bool(scene.content and scene.content.strip())
    if had_content and scene.checkpoint is None:
        scene.checkpoint = scene.content

    scene.content = inp["content"]
    scene.word_count = len(inp["content"].split()) if inp["content"] else 0
    await db.commit()
    resp: dict[str, Any] = {
        "scene_id": str(scene.id),
        "word_count": scene.word_count,
        "action": "updated_scene",
    }
    if had_content:
        resp["checkpointed"] = True
    return resp


async def _create_codex_entry(db: AsyncSession, inp: dict) -> dict:
    entry = CodexEntry(
        user_id=_owner_id(),
        name=inp["name"],
        entry_type=inp["entry_type"],
        description=inp.get("description", ""),
        content=inp.get("content", ""),
    )
    db.add(entry)
    await db.flush()
    await db.refresh(entry, ["associations"])

    if inp.get("work_id"):
        assoc = CodexAssociation(
            codex_entry_id=entry.id,
            target_type="work",
            target_id=uuid.UUID(inp["work_id"]),
        )
        db.add(assoc)

    await db.commit()
    await db.refresh(entry, ["associations"])
    return {
        "id": str(entry.id),
        "name": entry.name,
        "action": "created_codex_entry",
    }


async def _bulk_create_codex(db: AsyncSession, inp: dict) -> dict:
    work_id = uuid.UUID(inp["work_id"])
    entries_data = inp.get("entries", [])
    if not entries_data:
        return {"error": "No entries provided"}

    created = []
    for item in entries_data:
        entry = CodexEntry(
            user_id=_owner_id(),
            name=item["name"],
            entry_type=item["entry_type"],
            description=item.get("description", ""),
            content=item.get("content", ""),
        )
        db.add(entry)
        await db.flush()
        await db.refresh(entry, ["associations"])

        assoc = CodexAssociation(
            codex_entry_id=entry.id,
            target_type="work",
            target_id=work_id,
        )
        db.add(assoc)
        created.append({"id": str(entry.id), "name": entry.name, "type": entry.entry_type})

    await db.commit()
    return {
        "count": len(created),
        "entries": created,
        "action": "created_codex_bulk",
    }


async def _update_codex_entry(db: AsyncSession, inp: dict) -> dict:
    entry_id = uuid.UUID(inp["entry_id"])
    result = await db.execute(select(CodexEntry).where(CodexEntry.id == entry_id))
    entry = result.scalar_one_or_none()
    if not entry:
        return {"error": "Codex entry not found"}

    if "name" in inp:
        entry.name = inp["name"]
    if "description" in inp:
        entry.description = inp["description"]
    if "content" in inp:
        entry.content = inp["content"]

    await db.commit()
    return {"id": str(entry.id), "name": entry.name, "action": "updated_codex_entry"}


async def _summarize_work(db: AsyncSession, inp: dict) -> dict:
    work_id = uuid.UUID(inp["work_id"])
    result = await db.execute(
        select(Work)
        .where(Work.id == work_id)
        .options(
            selectinload(Work.chapters).selectinload(Chapter.scenes),
            selectinload(Work.sections),
        )
    )
    work = result.scalar_one_or_none()
    if not work:
        return {"error": "Work not found"}

    chapters = sorted(work.chapters, key=lambda c: c.sort_order)
    chapter_summaries = []
    total_words = 0
    for ch in chapters:
        scenes = sorted(ch.scenes, key=lambda s: s.sort_order)
        ch_words = sum(s.word_count for s in scenes)
        total_words += ch_words
        label = f"Chapter {ch.number}: {ch.title}" if ch.number else ch.title
        chapter_summaries.append({
            "title": label,
            "scenes": len(scenes),
            "words": ch_words,
            "synopsis": ch.synopsis or "",
            "content_preview": " ".join(
                s.content[:200] for s in scenes if s.content
            )[:500],
        })

    return {
        "title": work.title,
        "author": work.author,
        "description": work.description or "",
        "total_chapters": len(chapters),
        "total_words": total_words,
        "chapters": chapter_summaries,
        "action": "summarized_work",
    }


async def _list_works(db: AsyncSession, inp: dict) -> dict:
    stmt = select(Work).where(Work.user_id == _owner_id())
    if inp.get("series_id"):
        stmt = stmt.where(Work.series_id == uuid.UUID(inp["series_id"]))
    result = await db.execute(stmt.order_by(Work.sort_order))
    works = result.scalars().all()
    return {
        "works": [
            {"id": str(w.id), "title": w.title, "author": w.author}
            for w in works
        ],
    }


async def _list_series(db: AsyncSession, _inp: dict) -> dict:
    result = await db.execute(
        select(Series).where(Series.user_id == _owner_id()).order_by(Series.sort_order)
    )
    all_series = result.scalars().all()
    return {
        "series": [
            {"id": str(s.id), "title": s.title, "description": s.description or ""}
            for s in all_series
        ],
    }


async def _list_chapters(db: AsyncSession, inp: dict) -> dict:
    work_id = uuid.UUID(inp["work_id"])
    result = await db.execute(
        select(Chapter)
        .where(Chapter.work_id == work_id)
        .options(selectinload(Chapter.scenes))
        .order_by(Chapter.sort_order)
    )
    chapters = result.scalars().all()
    return {
        "chapters": [
            {
                "id": str(ch.id),
                "title": ch.title,
                "number": ch.number,
                "scenes": [
                    {"id": str(s.id), "title": s.title, "word_count": s.word_count}
                    for s in sorted(ch.scenes, key=lambda s: s.sort_order)
                ],
            }
            for ch in chapters
        ],
    }


async def _list_codex_entries(db: AsyncSession, inp: dict) -> dict:
    stmt = select(CodexEntry).where(CodexEntry.user_id == _owner_id())
    if inp.get("work_id"):
        stmt = (
            stmt.join(CodexAssociation, CodexAssociation.codex_entry_id == CodexEntry.id)
            .where(
                CodexAssociation.target_type == "work",
                CodexAssociation.target_id == uuid.UUID(inp["work_id"]),
            )
        )
    result = await db.execute(stmt)
    entries = result.scalars().all()
    return {
        "entries": [
            {
                "id": str(e.id),
                "name": e.name,
                "entry_type": e.entry_type.value,
                "description": e.description or "",
            }
            for e in entries
        ],
    }


async def _save_series_banner(
    db: AsyncSession, image_b64: str, mime_type: str, series_id: uuid.UUID
) -> dict:
    """Save a generated image as the series banner/cover."""
    import base64

    import aiofiles

    from app import paths
    from app.models.series import Series

    series = await db.get(Series, series_id)
    if not series:
        return {"error": "Series not found"}

    ext = ".png" if "png" in mime_type else ".jpg"
    filename = f"series_{series_id}{ext}"
    uploads_dir = paths.UPLOAD_DIR
    dest = uploads_dir / "covers" / filename
    dest.parent.mkdir(parents=True, exist_ok=True)

    if series.cover_image_path:
        old = uploads_dir / series.cover_image_path.lstrip("/uploads/")
        if old.exists():
            old.unlink()

    async with aiofiles.open(dest, "wb") as f:
        await f.write(base64.b64decode(image_b64))

    relative_path = f"/uploads/covers/{filename}"
    series.cover_image_path = relative_path
    await db.commit()

    return {"path": relative_path, "series_id": str(series_id)}


async def _generate_image(db: AsyncSession, inp: dict) -> dict:
    import base64

    from sqlalchemy import select
    from sqlalchemy.orm import selectinload

    from app import paths
    from app.models.codex import CodexEntry
    from app.services.image_gen import generate_image, save_generated_image

    prompt = inp["prompt"]
    negative_prompt = inp.get("negative_prompt", "")
    work_id = inp.get("work_id")
    codex_entry_id = inp.get("codex_entry_id")
    series_id = inp.get("series_id")
    width = inp.get("width", 1024)
    height = inp.get("height", 1024)
    alt_text = inp.get("alt_text", "")
    reference_codex_ids = inp.get("reference_codex_ids", [])

    if not work_id and not codex_entry_id and not series_id:
        return {"error": "Must provide work_id, codex_entry_id, or series_id"}

    reference_images: list[dict] = []
    uploads_dir = paths.UPLOAD_DIR
    for ref_id in reference_codex_ids:
        try:
            result = await db.execute(
                select(CodexEntry)
                .where(CodexEntry.id == uuid.UUID(ref_id))
                .options(selectinload(CodexEntry.images))
            )
            entry = result.scalar_one_or_none()
            if not entry:
                continue
            primary = next((img for img in entry.images if img.is_primary), None)
            if not primary:
                continue
            file_path = uploads_dir / "codex" / str(entry.id) / primary.filename
            if file_path.exists():
                image_bytes = file_path.read_bytes()
                reference_images.append({
                    "data": base64.b64encode(image_bytes).decode(),
                    "mime_type": primary.mime_type,
                    "name": entry.name,
                })
        except Exception:
            continue

    result = await generate_image(
        db, prompt,
        negative_prompt=negative_prompt,
        width=width,
        height=height,
        reference_images=reference_images if reference_images else None,
    )

    # Save to the destination
    if series_id:
        save_result = await _save_series_banner(
            db, result["data"], result["mime_type"], uuid.UUID(series_id)
        )
    else:
        save_result = await save_generated_image(
            db,
            result["data"],
            result["mime_type"],
            work_id=uuid.UUID(work_id) if work_id else None,
            codex_entry_id=uuid.UUID(codex_entry_id) if codex_entry_id else None,
            alt_text=alt_text,
        )

    # Return result with base64 for display in chat
    save_result["image_data"] = result["data"]
    save_result["mime_type"] = result["mime_type"]
    save_result["action"] = "generated_image"
    return save_result


_MD_INLINE_RE = re.compile(r"(?<!\w)[*_]{1,3}|[*_]{1,3}(?!\w)")


_NORMALIZE_MAP = str.maketrans({
    "\u2018": "'", "\u2019": "'", "\u201c": '"', "\u201d": '"',
    "\u2026": "...", "\u2014": "---", "\u2013": "--",
})


def _strip_md(text: str) -> str:
    """Strip inline markdown markers (bold/italic asterisks and underscores)."""
    return _MD_INLINE_RE.sub("", text)


def _normalize(text: str) -> str:
    return _strip_md(text).translate(_NORMALIZE_MAP)


def _find_anchor(content: str, anchor: str, anchor_from: int = 0, anchor_to: int = 0) -> tuple[int, int]:
    """Find anchor text in content, falling back to stripped/normalized matching."""
    idx = content.find(anchor)
    if idx != -1:
        return idx, len(anchor)

    stripped = _strip_md(anchor)
    if stripped != anchor:
        idx = content.find(stripped)
        if idx != -1:
            return idx, len(stripped)

    norm_anchor = _normalize(anchor)
    norm_content = _normalize(content)
    idx_norm = norm_content.find(norm_anchor)
    if idx_norm != -1:
        raw_idx = content.find(norm_anchor)
        if raw_idx != -1:
            return raw_idx, len(norm_anchor)
        for i in range(max(0, idx_norm - 5), min(len(content), idx_norm + 5)):
            if _normalize(content[:i]) == norm_content[:idx_norm]:
                end_target = idx_norm + len(norm_anchor)
                for j in range(i + len(norm_anchor) - 5, min(len(content) + 1, i + len(norm_anchor) + 10)):
                    if _normalize(content[:j]) == norm_content[:end_target]:
                        return i, j - i
                break

    if anchor_from > 0 and anchor_to > anchor_from and anchor_to <= len(content):
        candidate = content[anchor_from:anchor_to]
        if candidate.strip() == anchor.strip() or _normalize(candidate).strip() == norm_anchor.strip():
            return anchor_from, anchor_to - anchor_from

    return -1, 0


async def _review_scene(db: AsyncSession, inp: dict) -> dict:
    from app.models.comment import Comment

    scene_id = uuid.UUID(inp["scene_id"])
    result = await db.execute(select(Scene).where(Scene.id == scene_id))
    scene = result.scalar_one_or_none()
    if not scene:
        return {"error": "Scene not found"}

    raw_comments = inp.get("comments", [])
    if not raw_comments:
        return {"error": "No comments provided"}

    content = scene.content or ""
    created = []
    for item in raw_comments:
        raw_anchor = item["anchor_text"]
        anchor_text = _strip_md(raw_anchor)
        idx, length = _find_anchor(content, raw_anchor)
        if idx == -1:
            anchor_from = 0
            anchor_to = 0
        else:
            anchor_from = idx
            anchor_to = idx + length
            anchor_text = content[anchor_from:anchor_to]

        comment = Comment(
            scene_id=scene_id,
            anchor_text=anchor_text,
            anchor_from=anchor_from,
            anchor_to=anchor_to,
            content=item["content"],
            suggestion=item.get("suggestion"),
            author="ai",
        )
        db.add(comment)
        created.append({
            "anchor_text": anchor_text,
            "content": item["content"],
            "suggestion": item.get("suggestion"),
            "anchor_from": anchor_from,
            "anchor_to": anchor_to,
        })

    await db.commit()
    return {
        "scene_id": str(scene_id),
        "comments_created": len(created),
        "comments": created,
        "action": "reviewed_scene",
    }


async def _review_chapter(db: AsyncSession, inp: dict) -> dict:
    from app.models.comment import Comment

    chapter_id = uuid.UUID(inp["chapter_id"])
    result = await db.execute(
        select(Chapter)
        .where(Chapter.id == chapter_id)
        .options(selectinload(Chapter.scenes))
    )
    chapter = result.scalar_one_or_none()
    if not chapter:
        return {"error": "Chapter not found"}

    scene_map = {str(s.id): s for s in chapter.scenes}
    total_created = 0
    scene_results = []

    for group in inp.get("scene_comments", []):
        sid = group["scene_id"]
        scene = scene_map.get(sid)
        if not scene:
            scene_results.append({"scene_id": sid, "error": "not found"})
            continue

        content = scene.content or ""
        count = 0
        for item in group.get("comments", []):
            raw_anchor = item["anchor_text"]
            anchor_text = _strip_md(raw_anchor)
            idx, length = _find_anchor(content, raw_anchor)
            if idx == -1:
                anchor_from = 0
                anchor_to = 0
            else:
                anchor_from = idx
                anchor_to = idx + length
                anchor_text = content[anchor_from:anchor_to]

            comment = Comment(
                scene_id=uuid.UUID(sid),
                anchor_text=anchor_text,
                anchor_from=anchor_from,
                anchor_to=anchor_to,
                content=item["content"],
                suggestion=item.get("suggestion"),
                author="ai",
            )
            db.add(comment)
            count += 1

        total_created += count
        scene_results.append({"scene_id": sid, "comments_created": count})

    await db.commit()
    return {
        "chapter_id": str(chapter_id),
        "total_comments_created": total_created,
        "scenes": scene_results,
        "action": "reviewed_chapter",
    }


_HANDLERS = {
    "create_series": _create_series,
    "create_work": _create_work,
    "create_chapter": _create_chapter,
    "write_scene": _write_scene,
    "create_codex_entry": _create_codex_entry,
    "bulk_create_codex": _bulk_create_codex,
    "update_codex_entry": _update_codex_entry,
    "summarize_work": _summarize_work,
    "list_works": _list_works,
    "list_series": _list_series,
    "list_chapters": _list_chapters,
    "list_codex_entries": _list_codex_entries,
    "generate_image": _generate_image,
    "review_scene": _review_scene,
    "review_chapter": _review_chapter,
}
