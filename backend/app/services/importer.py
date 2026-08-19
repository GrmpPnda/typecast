from __future__ import annotations

import logging
import re
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.chapter import Chapter
from app.models.scene import Scene
from app.models.work import Work
from app.repositories.sqlalchemy_repo import SQLAlchemyRepository
from app.services.ai import get_ai_provider

logger = logging.getLogger(__name__)

IMPORT_PROMPT = """\
Analyze this manuscript and identify its structure. Do NOT return the content itself.
Return a JSON object describing the structure using line numbers (0-indexed) from the original text.

{
  "title": "the work's title (infer from content or use 'Untitled')",
  "author": "author name if found, otherwise 'Unknown'",
  "description": "a brief 1-2 sentence summary",
  "chapters": [
    {
      "title": "chapter title or null if just numbered",
      "number": 1,
      "start_line": 10,
      "scenes": [
        {
          "title": "scene break title or null",
          "start_line": 10,
          "end_line": 45
        }
      ]
    }
  ]
}

Rules:
- Use line numbers to mark where each chapter and scene starts/ends
- A chapter's content runs from its start_line to the next chapter's start_line (or end of document)
- If a chapter has no sub-scenes (no ### headings), create one scene spanning the whole chapter
- Each scene's end_line is exclusive (content is lines[start_line:end_line])
- Chapter numbers should be sequential starting at 1
- If a chapter heading is just "Chapter 1" or "Chapter One", set title to null and use the number
- If a chapter has a name like "Chapter 3: The Storm", set number to 3 and title to "The Storm"
- Look for # or ## as chapter headings, ### as scene breaks
- Front/back matter sections (Dedication, Preface, Epilogue, etc.) should be chapters too
- The start_line for a chapter/scene should be the line AFTER the heading
"""

_CHAPTER_NUM_RE = re.compile(
    r"^Chapter\s+(\w+)(?:[:\s—–-]+(.+))?$", re.IGNORECASE
)

_WORD_NUMBERS = {
    "one": 1, "two": 2, "three": 3, "four": 4, "five": 5,
    "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10,
    "eleven": 11, "twelve": 12, "thirteen": 13, "fourteen": 14, "fifteen": 15,
    "sixteen": 16, "seventeen": 17, "eighteen": 18, "nineteen": 19, "twenty": 20,
}


def _parse_chapter_heading(heading: str, fallback_number: int) -> tuple[str | None, int]:
    m = _CHAPTER_NUM_RE.match(heading)
    if not m:
        return heading, fallback_number

    num_str = m.group(1)
    title = m.group(2).strip() if m.group(2) else None

    if num_str.isdigit():
        return title, int(num_str)

    word_num = _WORD_NUMBERS.get(num_str.lower())
    if word_num is not None:
        return title, word_num

    return heading, fallback_number


def _detect_heading_level(lines: list[str]) -> int:
    h1_count = 0
    h2_count = 0
    for line in lines:
        stripped = line.strip()
        if re.match(r"^##\s+", stripped):
            h2_count += 1
        elif re.match(r"^#\s+", stripped):
            h1_count += 1

    if h1_count >= 2:
        return 1
    if h2_count >= 2:
        return 2
    return 2


_HR_RE = re.compile(r"^[-*_]{3,}\s*$")


def _fallback_parse(content: str) -> dict[str, Any]:
    lines = content.split("\n")
    chapter_level = _detect_heading_level(lines)

    if chapter_level == 1:
        chapter_re = re.compile(r"^#\s+(.+)$")
        scene_re = re.compile(r"^##\s+(.+)$")
    else:
        chapter_re = re.compile(r"^##\s+(.+)$")
        scene_re = re.compile(r"^###\s+(.+)$")

    title = "Imported Work"
    author = "Unknown"
    start_line = 0

    # Single H1 = book title; multiple H1s = chapter markers (handled by chapter_level == 1)
    if chapter_level == 2:
        first_line = lines[0].strip() if lines else ""
        h1_match = re.match(r"^#\s+(.+)$", first_line)
        if h1_match:
            title = h1_match.group(1).strip()
            start_line = 1
        else:
            bold_match = re.match(r"^\*\*(.+?)\.?\*\*", first_line)
            if bold_match:
                title = bold_match.group(1).strip()

    chapters: list[dict[str, Any]] = []
    current_chapter: dict[str, Any] | None = None
    current_scene_start: int = start_line
    current_scene_title: str | None = None
    scenes_buffer: list[dict[str, Any]] = []

    def flush_scene(end_line: int) -> None:
        nonlocal current_scene_start, current_scene_title
        scene_lines = lines[current_scene_start:end_line]
        text = "\n".join(scene_lines).strip()
        if text:
            scenes_buffer.append({"title": current_scene_title, "content": text})
        current_scene_title = None

    def flush_chapter(end_line: int) -> None:
        nonlocal current_chapter, scenes_buffer
        flush_scene(end_line)
        if current_chapter is not None:
            current_chapter["scenes"] = scenes_buffer
            if current_chapter["scenes"]:
                chapters.append(current_chapter)
        scenes_buffer = []

    def ensure_chapter() -> None:
        nonlocal current_chapter
        if current_chapter is None:
            current_chapter = {
                "title": None,
                "number": len(chapters) + 1,
                "scenes": [],
            }

    for i, line in enumerate(lines):
        if i < start_line:
            continue

        stripped = line.strip()

        if not stripped or stripped == "#":
            continue

        chapter_match = chapter_re.match(stripped)
        scene_match = scene_re.match(stripped)
        is_hr = _HR_RE.match(stripped)

        if chapter_match:
            flush_chapter(i)

            heading = chapter_match.group(1).strip()
            if heading.startswith("!"):
                current_scene_start = i + 1
                continue

            chapter_num = len(chapters) + 1
            chapter_title, chapter_num = _parse_chapter_heading(heading, chapter_num)

            current_chapter = {
                "title": chapter_title,
                "number": chapter_num,
                "scenes": [],
            }
            current_scene_start = i + 1
            current_scene_title = None
            continue

        if scene_match:
            ensure_chapter()
            flush_scene(i)
            current_scene_start = i + 1
            current_scene_title = scene_match.group(1).strip()
            continue

        if is_hr:
            ensure_chapter()
            flush_scene(i)
            current_scene_start = i + 1
            current_scene_title = None
            continue

    flush_chapter(len(lines))

    if not chapters:
        text = "\n".join(lines[start_line:]).strip()
        chapters = [
            {
                "title": None,
                "number": 1,
                "scenes": [{"title": None, "content": text}],
            }
        ]

    return {
        "title": title,
        "author": author,
        "description": None,
        "chapters": chapters,
    }


def _apply_ai_structure(
    lines: list[str], structure: dict[str, Any]
) -> dict[str, Any]:
    chapters = []
    for ch_data in structure.get("chapters", []):
        scenes = []
        for sc_data in ch_data.get("scenes", []):
            start = sc_data.get("start_line", 0)
            end = sc_data.get("end_line", len(lines))
            text = "\n".join(lines[start:end]).strip()
            scenes.append({"title": sc_data.get("title"), "content": text})

        if not scenes:
            chapters.append({
                "title": ch_data.get("title"),
                "number": ch_data.get("number"),
                "scenes": [{"title": None, "content": ""}],
            })
        else:
            chapters.append({
                "title": ch_data.get("title"),
                "number": ch_data.get("number"),
                "scenes": scenes,
            })

    structure["chapters"] = chapters
    return structure


async def import_markdown(
    content: str,
    db: AsyncSession,
    use_ai: bool = True,
    author_override: str | None = None,
    title_override: str | None = None,
) -> Work:
    lines = content.split("\n")
    structure: dict[str, Any]

    if use_ai:
        try:
            provider = get_ai_provider()
            numbered_content = "\n".join(
                f"{i}: {line}" for i, line in enumerate(lines)
            )
            raw_structure = await provider.parse_structured(
                IMPORT_PROMPT, numbered_content
            )
            structure = _apply_ai_structure(lines, raw_structure)
        except Exception:
            logger.exception("AI import failed, falling back to regex parser")
            structure = _fallback_parse(content)
    else:
        structure = _fallback_parse(content)

    work_repo = SQLAlchemyRepository(db, Work)
    chapter_repo = SQLAlchemyRepository(db, Chapter)
    scene_repo = SQLAlchemyRepository(db, Scene)

    work = await work_repo.create(
        title=title_override or structure.get("title", "Untitled"),
        author=author_override or structure.get("author", "Unknown"),
        description=structure.get("description"),
    )

    for ch_idx, ch_data in enumerate(structure.get("chapters", [])):
        chapter = await chapter_repo.create(
            work_id=work.id,
            title=ch_data.get("title") or "",
            number=ch_data.get("number", ch_idx + 1),
            sort_order=ch_idx,
        )

        for sc_idx, sc_data in enumerate(ch_data.get("scenes", [])):
            scene_content = sc_data.get("content", "")
            await scene_repo.create(
                chapter_id=chapter.id,
                title=sc_data.get("title"),
                content=scene_content,
                sort_order=sc_idx,
                word_count=len(scene_content.split()) if scene_content else 0,
            )

    await db.refresh(work)
    return work
