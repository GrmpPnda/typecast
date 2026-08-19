from __future__ import annotations

import base64
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app import paths
from app.models.chapter import Chapter
from app.models.codex import CodexEntry
from app.models.codex_association import CodexAssociation
from app.models.scene import Scene
from app.models.work import Work


async def _get_codex_for_work(
    db: AsyncSession, work_id: uuid.UUID, series_id: uuid.UUID | None = None
) -> list[CodexEntry]:
    from sqlalchemy import or_

    conditions = [
        (CodexAssociation.target_type == "work") & (CodexAssociation.target_id == work_id)
    ]
    if series_id:
        conditions.append(
            (CodexAssociation.target_type == "series") & (CodexAssociation.target_id == series_id)
        )

    result = await db.execute(
        select(CodexEntry)
        .join(CodexAssociation, CodexAssociation.codex_entry_id == CodexEntry.id)
        .where(or_(*conditions))
        .options(selectinload(CodexEntry.images))
    )
    return list(result.unique().scalars().all())


def _strip(text: str | None) -> str:
    return (text or "").strip()


async def assemble_work_context(
    db: AsyncSession,
    work_id: uuid.UUID,
    *,
    include_full_text: bool = False,
    chapter_id: uuid.UUID | None = None,
    scene_id: uuid.UUID | None = None,
    max_scene_chars: int = 3000,
) -> str:
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
        return ""

    parts: list[str] = []

    parts.append(f"# {work.title}")
    if work.author:
        parts.append(f"Author: {work.author}")
    if _strip(work.description):
        parts.append(f"\n## Description\n{work.description}")
    if _strip(work.blurb):
        parts.append(f"\n## Blurb\n{work.blurb}")

    ai_instructions_parts: list[str] = []
    if work.series_id:
        from app.models.series import Series
        series_result = await db.execute(
            select(Series).where(Series.id == work.series_id)
        )
        series = series_result.scalar_one_or_none()
        if series and _strip(series.ai_instructions):
            ai_instructions_parts.append(
                f"### Series-Level Instructions\n{series.ai_instructions}"
            )
    if _strip(work.ai_instructions):
        ai_instructions_parts.append(
            f"### Work-Level Instructions\n{work.ai_instructions}"
        )
    if ai_instructions_parts:
        parts.append(
            "\n## Author's AI Instructions\n"
            + "\n\n".join(ai_instructions_parts)
        )

    codex_entries = await _get_codex_for_work(db, work_id, work.series_id)
    if codex_entries:
        parts.append("\n## Codex (World-Building Reference)")
        for entry in codex_entries:
            has_primary = any(img.is_primary for img in entry.images) if entry.images else False
            img_tag = " [has reference image]" if has_primary else ""
            line = f"- **{entry.name}** ({entry.entry_type.value}, id={entry.id}){img_tag}"
            if _strip(entry.description):
                line += f": {entry.description}"
            parts.append(line)
            if _strip(entry.content):
                parts.append(f"  {entry.content[:500]}")

    front_matter = sorted(
        [s for s in work.sections if s.placement and s.placement.value == "front_matter"],
        key=lambda s: s.sort_order,
    )
    back_matter = sorted(
        [s for s in work.sections if s.placement and s.placement.value == "back_matter"],
        key=lambda s: s.sort_order,
    )

    if front_matter:
        parts.append("\n## Front Matter")
        for sec in front_matter:
            title = sec.title or sec.section_type.value.replace("_", " ").title()
            parts.append(f"### {title}")
            if _strip(sec.content):
                parts.append(sec.content[:1000])

    chapters = sorted(work.chapters, key=lambda c: c.sort_order)
    if chapters:
        parts.append("\n## Chapters")

        focus_chapter_id = chapter_id
        if scene_id and not focus_chapter_id:
            for ch in chapters:
                for sc in ch.scenes:
                    if str(sc.id) == str(scene_id):
                        focus_chapter_id = ch.id
                        break

        for ch in chapters:
            label = f"Chapter {ch.number}" if ch.number else ch.title
            if ch.title and ch.number:
                label += f": {ch.title}"

            is_focus = focus_chapter_id and str(ch.id) == str(focus_chapter_id)
            scenes = sorted(ch.scenes, key=lambda s: s.sort_order)

            if include_full_text or is_focus:
                parts.append(f"\n### {label} (chapter_id={ch.id})")
                if _strip(ch.synopsis):
                    parts.append(f"*Synopsis: {ch.synopsis}*")
                for idx, sc in enumerate(scenes):
                    scene_label = sc.title or f"Scene {idx + 1}"
                    parts.append(f"#### {scene_label} (scene_id={sc.id})")
                    content = _strip(sc.content)
                    if content:
                        if is_focus and not include_full_text:
                            parts.append(content[:max_scene_chars])
                        else:
                            parts.append(content)
            else:
                synopsis = f" — {ch.synopsis}" if _strip(ch.synopsis) else ""
                scene_count = len(scenes)
                sc_word = "scenes" if scene_count != 1 else "scene"
                parts.append(
                    f"- {label} (chapter_id={ch.id}, {scene_count} {sc_word}){synopsis}"
                )

    if back_matter:
        parts.append("\n## Back Matter")
        for sec in back_matter:
            title = sec.title or sec.section_type.value.replace("_", " ").title()
            parts.append(f"### {title}")
            if _strip(sec.content):
                parts.append(sec.content[:1000])

    return "\n".join(parts)


async def assemble_scene_context(
    db: AsyncSession,
    scene_id: uuid.UUID,
    *,
    include_surrounding: bool = True,
    max_chars: int = 4000,
) -> str:
    result = await db.execute(
        select(Scene).where(Scene.id == scene_id)
    )
    scene = result.scalar_one_or_none()
    if not scene:
        return ""

    result = await db.execute(
        select(Chapter)
        .where(Chapter.id == scene.chapter_id)
        .options(selectinload(Chapter.scenes))
    )
    chapter = result.scalar_one_or_none()
    if not chapter:
        return ""

    parts: list[str] = []
    scenes = sorted(chapter.scenes, key=lambda s: s.sort_order)
    scene_idx = next(
        (i for i, s in enumerate(scenes) if str(s.id) == str(scene_id)), 0
    )

    if include_surrounding and len(scenes) > 1:
        parts.append(
            "## Full Chapter Context\n"
            "All scenes in this chapter are listed below. "
            "The CURRENT scene is marked. Use this context to ensure "
            "consistency in tone, character voice, pacing, and continuity.\n"
        )
        for i, sc in enumerate(scenes):
            label = sc.title or f"Scene {i + 1}"
            is_current = i == scene_idx
            marker = " ← CURRENT SCENE" if is_current else ""
            parts.append(
                f"### {label} (scene_id={sc.id}){marker}"
            )
            content = _strip(sc.content)
            if content:
                if is_current:
                    parts.append(content)
                else:
                    parts.append(content[:max_chars])
            parts.append("")
    else:
        parts.append("## Current Scene")
        if scene.title:
            parts.append(f"### {scene.title}")
        current_content = _strip(scene.content)
        if current_content:
            parts.append(current_content)

    return "\n".join(parts)


async def resolve_mentions(
    db: AsyncSession, mentions: list,
) -> dict:
    """Resolve @mentions into context text and images for the AI.

    Returns ``{"text": "...", "images": [{"data": ..., "mime_type": ..., "name": ...}]}``.
    """
    if not mentions:
        return {"text": "", "images": []}

    sections: list[str] = []
    images: list[dict] = []

    for mention in mentions:
        m_type = mention.type
        m_id = mention.id

        if m_type == "codex":
            result = await db.execute(
                select(CodexEntry)
                .where(CodexEntry.id == m_id)
                .options(selectinload(CodexEntry.images))
            )
            entry = result.scalar_one_or_none()
            if not entry:
                continue
            lines = [f"### @Mentioned: {entry.name} ({entry.entry_type.value})"]
            if _strip(entry.description):
                lines.append(f"**Description:** {entry.description}")
            if _strip(entry.content):
                lines.append(entry.content)
            primary = next(
                (img for img in entry.images if img.is_primary), None,
            )
            if primary:
                file_path = (
                    paths.UPLOAD_DIR / "codex" / str(entry.id) / primary.filename
                )
                try:
                    file_bytes = file_path.read_bytes()
                    encoded = base64.b64encode(file_bytes).decode()
                    images.append({
                        "data": encoded,
                        "mime_type": primary.mime_type,
                        "name": entry.name,
                    })
                    lines.append("Primary image: [included as image attachment]")
                except (FileNotFoundError, OSError):
                    lines.append(f"Primary image: {primary.url}")
            sections.append("\n".join(lines))

        elif m_type == "chapter":
            result = await db.execute(
                select(Chapter)
                .where(Chapter.id == m_id)
                .options(selectinload(Chapter.scenes))
            )
            chapter = result.scalar_one_or_none()
            if not chapter:
                continue
            label = chapter.title or f"Chapter {chapter.number}"
            lines = [f"### @Mentioned: {label} (chapter)"]
            if chapter.number:
                lines.append(f"**Number:** {chapter.number}")
            if _strip(chapter.synopsis):
                lines.append(f"**Synopsis:** {chapter.synopsis}")
            for sc in sorted(chapter.scenes, key=lambda s: s.sort_order):
                if sc.title:
                    lines.append(f"#### {sc.title}")
                content = _strip(sc.content)
                if content:
                    lines.append(content)
            sections.append("\n".join(lines))

        elif m_type == "scene":
            result = await db.execute(
                select(Scene).where(Scene.id == m_id)
            )
            scene = result.scalar_one_or_none()
            if not scene:
                continue
            label = scene.title or "Untitled Scene"
            lines = [f"### @Mentioned: {label} (scene)"]
            content = _strip(scene.content)
            if content:
                lines.append(content)
            sections.append("\n".join(lines))

        elif m_type == "work":
            result = await db.execute(
                select(Work).where(Work.id == m_id)
            )
            work = result.scalar_one_or_none()
            if not work:
                continue
            lines = [f"### @Mentioned: {work.title} (work)"]
            if work.author:
                lines.append(f"**Author:** {work.author}")
            if _strip(work.description):
                lines.append(f"**Description:** {work.description}")
            if _strip(work.blurb):
                lines.append(f"**Blurb:** {work.blurb}")
            sections.append("\n".join(lines))

    return {"text": "\n\n".join(sections), "images": images}
