from __future__ import annotations

import os
import platform
import re
import uuid
from pathlib import Path

if platform.system() == "Darwin":
    _brew_lib = "/opt/homebrew/lib"
    if os.path.isdir(_brew_lib):
        os.environ.setdefault("DYLD_FALLBACK_LIBRARY_PATH", _brew_lib)

import markdown
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app import paths
from app.models.chapter import Chapter
from app.models.profile import Profile
from app.models.scene import Scene
from app.models.work import Work

MATTER_TITLES = {
    "dedication",
    "preface",
    "foreword",
    "introduction",
    "prologue",
    "epilogue",
    "afterword",
    "acknowledgments",
    "acknowledgements",
    "appendix",
    "glossary",
    "bibliography",
    "about the author",
    "also by",
    "colophon",
    "copyright",
    "half title",
    "title page",
}

FRONT_MATTER_TITLES = {
    "half title", "title page", "copyright", "dedication", "epigraph",
    "table of contents", "foreword", "preface", "acknowledgments",
    "acknowledgements", "introduction", "prologue",
}

BACK_MATTER_TITLES = {
    "epilogue", "afterword", "appendix", "glossary", "bibliography",
    "about the author", "also by", "colophon", "index",
}

CENTERED_TITLES = {
    "dedication",
    "epigraph",
    "half title",
    "title page",
}

UPLOAD_DIR = paths.UPLOAD_DIR


def _is_matter(title: str | None) -> bool:
    if not title:
        return False
    return title.lower().strip() in MATTER_TITLES


def _is_front_matter(title: str | None) -> bool:
    if not title:
        return False
    return title.lower().strip() in FRONT_MATTER_TITLES


def _is_back_matter(title: str | None) -> bool:
    if not title:
        return False
    return title.lower().strip() in BACK_MATTER_TITLES


def _is_centered(title: str | None) -> bool:
    if not title:
        return False
    return title.lower().strip() in CENTERED_TITLES


async def _load_work(db: AsyncSession, work_id: uuid.UUID) -> Work:
    """Load a work with its chapters and scenes, all eagerly fetched."""
    result = await db.execute(
        select(Work)
        .where(Work.id == work_id)
        .options(
            selectinload(Work.chapters).selectinload(Chapter.scenes),
        )
    )
    work = result.scalar_one_or_none()
    if work is None:
        raise WorkNotFoundError(work_id)
    return work


async def _load_profile(db: AsyncSession, profile_id: uuid.UUID) -> Profile:
    profile = await db.get(Profile, profile_id)
    if profile is None:
        raise ProfileNotFoundError(profile_id)
    return profile


def _sorted_chapters(work: Work) -> list[Chapter]:
    return sorted(work.chapters, key=lambda ch: ch.sort_order)


def _sorted_scenes(chapter: Chapter) -> list[Scene]:
    return sorted(chapter.scenes, key=lambda s: s.sort_order)


_IMAGE_ONLY_RE = re.compile(
    r"^!\[[^\]]*\]\([^)]+\)(\s*!\[[^\]]*\]\([^)]+\))*\s*$"
)


def _is_image_only(content: str | None) -> bool:
    """True if scene content contains only markdown image(s) and nothing else."""
    stripped = (content or "").strip()
    if not stripped:
        return False
    return bool(_IMAGE_ONLY_RE.match(stripped))


def _compress_image_bytes(
    data: bytes, *, max_width: int = 1200, quality: int = 75
) -> bytes:
    """Compress image data to JPEG, resizing if wider than max_width."""
    import io

    from PIL import Image

    img = Image.open(io.BytesIO(data))
    if img.mode in ("RGBA", "P"):
        img = img.convert("RGB")
    if img.width > max_width:
        ratio = max_width / img.width
        img = img.resize((max_width, round(img.height * ratio)), Image.LANCZOS)
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=quality, optimize=True)
    return buf.getvalue()


def _chapter_heading(chapter: Chapter) -> str | None:
    """Build the display heading for a chapter.

    Returns None if the chapter's title should be suppressed.
    - If show_title is False, no heading.
    - Matter chapters show just their title (no "Chapter N" prefix).
    - Body chapters show "Chapter N" (with title underneath if present and show_title).
    """
    if not chapter.show_title:
        return None

    if _is_matter(chapter.title):
        return chapter.title

    parts: list[str] = []
    if chapter.number is not None:
        parts.append(f"Chapter {chapter.number}")
    if chapter.title:
        parts.append(chapter.title)
    return "\n".join(parts) if parts else None


# ---------------------------------------------------------------------------
# Markdown export
# ---------------------------------------------------------------------------


def _strip_images(text: str) -> str:
    """Remove markdown image tags from text."""
    import re
    return re.sub(r"!\[[^\]]*\]\([^)]*\)", "", text)


def _build_markdown(work: Work, *, include_images: bool = False) -> str:
    lines: list[str] = []
    lines.append(f"# {work.title}\n")
    if work.author:
        lines.append(f"*by {work.author}*\n")
    lines.append("")

    chapters = _sorted_chapters(work)
    for i, chapter in enumerate(chapters):
        if i > 0:
            lines.append("\n---\n")

        heading = _chapter_heading(chapter)
        if heading:
            heading_lines = heading.split("\n")
            if _is_matter(chapter.title):
                lines.append(f"## {heading_lines[0]}\n")
            elif len(heading_lines) == 2:
                lines.append(f"## {heading_lines[0]}\n")
                lines.append(f"### {heading_lines[1]}\n")
            else:
                lines.append(f"## {heading_lines[0]}\n")

        scenes = _sorted_scenes(chapter)
        for j, scene in enumerate(scenes):
            if j > 0 and not _is_image_only(scenes[j - 1].content) and not _is_image_only(scene.content):
                lines.append("\n***\n")
            content = (scene.content or "").strip()
            if not include_images:
                content = _strip_images(content).strip()
            if content:
                lines.append(content)
                lines.append("")

    return "\n".join(lines)


async def export_markdown(
    db: AsyncSession, work_id: uuid.UUID, *, include_images: bool = False
) -> tuple[str, str]:
    """Return (content_string, suggested_filename)."""
    work = await _load_work(db, work_id)
    content = _build_markdown(work, include_images=include_images)
    filename = _safe_filename(work.title) + ".md"
    return content, filename


# ---------------------------------------------------------------------------
# Plain text export
# ---------------------------------------------------------------------------


def _build_plaintext(work: Work) -> str:
    lines: list[str] = []
    lines.append(work.title.upper())
    if work.author:
        lines.append(f"by {work.author}")
    lines.append("")
    lines.append("")

    chapters = _sorted_chapters(work)
    for i, chapter in enumerate(chapters):
        if i > 0:
            lines.append("")
            lines.append("* * *")
            lines.append("")

        heading = _chapter_heading(chapter)
        if heading:
            for heading_line in heading.split("\n"):
                lines.append(heading_line)
            lines.append("")

        scenes = _sorted_scenes(chapter)
        for j, scene in enumerate(scenes):
            if j > 0 and not _is_image_only(scenes[j - 1].content) and not _is_image_only(scene.content):
                lines.append("")
                lines.append("***")
                lines.append("")
            content = (scene.content or "").strip()
            if content:
                # Strip markdown formatting for plain text
                lines.append(_strip_markdown(content))

    return "\n".join(lines)


def _strip_markdown(text: str) -> str:
    """Minimal markdown stripping for plain text output."""
    import re

    # Remove image references, keep alt text
    text = re.sub(r"!\[([^\]]*)\]\([^)]*\)", r"[\1]", text)
    # Remove link formatting, keep text
    text = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", text)
    # Remove bold/italic markers
    text = re.sub(r"\*{1,3}([^*]+)\*{1,3}", r"\1", text)
    text = re.sub(r"_{1,3}([^_]+)_{1,3}", r"\1", text)
    return text


async def export_plaintext(db: AsyncSession, work_id: uuid.UUID) -> tuple[str, str]:
    work = await _load_work(db, work_id)
    content = _build_plaintext(work)
    filename = _safe_filename(work.title) + ".txt"
    return content, filename


# ---------------------------------------------------------------------------
# HTML export
# ---------------------------------------------------------------------------

_HTML_TEMPLATE = """\
<!DOCTYPE html>
<html lang="{lang}">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title}</title>
<style>
  body {{
    max-width: 42em;
    margin: 2em auto;
    padding: 0 1em;
    font-family: Georgia, serif;
    font-size: 1.1em;
    line-height: 1.6;
    color: #222;
  }}
  h1 {{ text-align: center; margin-bottom: 0.2em; }}
  .author {{ text-align: center; font-style: italic; margin-bottom: 2em; color: #555; }}
  .chapter {{ page-break-before: always; margin-top: 3em; }}
  .chapter:first-of-type {{ page-break-before: avoid; margin-top: 1em; }}
  .chapter-number {{ text-align: center; font-size: 1.2em; letter-spacing: 0.1em;
                     text-transform: uppercase; margin-bottom: 0.2em; color: #555; }}
  .chapter-title {{ text-align: center; font-size: 1.4em; margin-bottom: 1.5em; }}
  .scene-break {{ text-align: center; margin: 1.5em 0; color: #999; letter-spacing: 0.5em; }}
  hr {{ border: none; border-top: 1px solid #ddd; margin: 2em 0; }}
  img {{ max-width: 100%; height: auto; }}
  .centered-content {{ text-align: center; }}
  .centered-content p {{ text-indent: 0; }}
</style>
</head>
<body>
<h1>{title}</h1>
{author_html}
{body}
</body>
</html>
"""


def _md_to_html(md_text: str) -> str:
    """Convert markdown content to HTML, resolving image paths."""
    return markdown.markdown(md_text, extensions=["tables", "fenced_code"])


def _build_html_body(work: Work) -> str:
    parts: list[str] = []
    chapters = _sorted_chapters(work)

    for chapter in chapters:
        chapter_parts: list[str] = []
        if _is_centered(chapter.title):
            chapter_parts.append('<div class="chapter centered-content">')
        else:
            chapter_parts.append('<div class="chapter">')

        heading = _chapter_heading(chapter)
        if heading:
            heading_lines = heading.split("\n")
            if _is_matter(chapter.title):
                chapter_parts.append(
                    f'<div class="chapter-title">{_escape_html(heading_lines[0])}</div>'
                )
            elif len(heading_lines) == 2:
                chapter_parts.append(
                    f'<div class="chapter-number">{_escape_html(heading_lines[0])}</div>'
                )
                chapter_parts.append(
                    f'<div class="chapter-title">{_escape_html(heading_lines[1])}</div>'
                )
            else:
                chapter_parts.append(
                    f'<div class="chapter-number">{_escape_html(heading_lines[0])}</div>'
                )

        scenes = _sorted_scenes(chapter)
        for j, scene in enumerate(scenes):
            content = (scene.content or "").strip()
            is_img = _is_image_only(content)
            prev_img = j > 0 and _is_image_only(scenes[j - 1].content)
            if j > 0 and not prev_img and not is_img:
                chapter_parts.append('<div class="scene-break">***</div>')
            if content:
                html = _md_to_html(content)
                if is_img:
                    html = f'<div class="full-page-image">{html}</div>'
                chapter_parts.append(html)

        chapter_parts.append("</div>")
        parts.append("\n".join(chapter_parts))

    return "\n\n".join(parts)


async def export_html(db: AsyncSession, work_id: uuid.UUID) -> tuple[str, str]:
    work = await _load_work(db, work_id)
    body = _build_html_body(work)
    author_html = f'<div class="author">by {_escape_html(work.author)}</div>' if work.author else ""
    html = _HTML_TEMPLATE.format(
        lang=work.language or "en",
        title=_escape_html(work.title),
        author_html=author_html,
        body=body,
    )
    filename = _safe_filename(work.title) + ".html"
    return html, filename


# ---------------------------------------------------------------------------
# PDF export (WeasyPrint)
# ---------------------------------------------------------------------------


def _header_content_css(value: str, work_title: str, work_author: str) -> str:
    """Return a CSS content expression for a running header value."""
    if value == "title":
        return f'"{_escape_css_string(work_title)}"'
    if value == "author":
        return f'"{_escape_css_string(work_author)}"'
    if value == "chapter":
        return "string(chapter-number)"
    if value == "chapter_title":
        return "string(chapter-title)"
    if value == "page_number":
        return "counter({counter})"
    return '""'


def _escape_css_string(s: str) -> str:
    return s.replace("\\", "\\\\").replace('"', '\\"')


def _build_pdf_css(profile: Profile, work: Work | None = None) -> str:
    """Generate CSS from a profile's page/font settings."""
    pw = f"{profile.page_width}in" if profile.page_width else "6in"
    ph = f"{profile.page_height}in" if profile.page_height else "9in"
    mi = f"{profile.margin_inner}in" if profile.margin_inner else "0.875in"
    mo = f"{profile.margin_outer}in" if profile.margin_outer else "0.625in"
    ff = profile.font_family or "Georgia, serif"
    fs = profile.font_size or "11pt"
    lh = profile.line_height or 1.5

    pn = getattr(profile, "page_numbers", False)
    pn_start = getattr(profile, "page_numbers_start_at_content", True)

    h_recto = getattr(profile, "header_recto", None)
    h_verso = getattr(profile, "header_verso", None)
    h_position = getattr(profile, "header_position", "outer") or "outer"
    has_headers = bool(h_recto or h_verso)

    f_recto = getattr(profile, "footer_recto", None) or ""
    f_verso = getattr(profile, "footer_verso", None) or ""
    f_position = getattr(profile, "footer_position", "center") or "center"
    has_footers = bool(f_recto or f_verso)

    h_ff = getattr(profile, "header_font_family", None) or ff
    h_fs = getattr(profile, "header_font_size", None) or "9pt"
    h_fw = getattr(profile, "header_font_weight", None) or ""

    raw_mt = float(profile.margin_top or 0.75)
    raw_mb = float(profile.margin_bottom or 0.75)
    hdr_from_edge = float(getattr(profile, "header_from_edge", None) or 0.3)
    ftr_from_edge = float(getattr(profile, "footer_from_edge", None) or 0.3)
    body_mt = f"{hdr_from_edge + raw_mt}in" if has_headers else f"{raw_mt}in"
    body_mb = f"{ftr_from_edge + raw_mb}in" if has_footers else f"{raw_mb}in"
    mt = f"{raw_mt}in"
    mb = f"{raw_mb}in"

    w_title = (work.title if work else "") or ""
    w_author = (work.author if work else "") or ""

    fm_roman = bool(getattr(profile, "front_matter_roman", False)) and pn and pn_start
    counter = "pgnum" if pn and pn_start else "page"
    fm_counter = "fmpage" if fm_roman else counter

    def _hdr(value: str, cnt: str | None = None) -> str:
        raw = _header_content_css(value, w_title, w_author)
        c = cnt or counter
        if c == "fmpage":
            raw = raw.replace(
                "counter({counter})", "counter(fmpage, lower-roman)"
            )
            return raw.replace("{counter}", c)
        return raw.replace("{counter}", c)

    h_fw_css = f"font-weight: {h_fw};" if h_fw else ""
    hdr_style = (
        f"font-family: {h_ff}; font-size: {h_fs}; {h_fw_css} color: #444; "
        f"vertical-align: top; padding-top: {hdr_from_edge}in;"
    )
    ftr_style = (
        f"font-family: {h_ff}; font-size: {h_fs}; {h_fw_css} color: #444; "
        f"vertical-align: bottom; padding-bottom: {ftr_from_edge}in;"
    )

    def _margin_box_slots(recto_val: str | None, verso_val: str | None,
                          position: str, zone: str, style: str,
                          page_type: str = "", cnt: str | None = None) -> str:
        if not recto_val and not verso_val:
            return ""
        prefix = "top" if zone == "header" else "bottom"
        lines = []
        if position == "center":
            if recto_val:
                lines.append(
                    f"@page {page_type}:right {{ @{prefix}-center "
                    f"{{ content: {_hdr(recto_val, cnt)}; {style} }} }}"
                )
            if verso_val:
                lines.append(
                    f"@page {page_type}:left {{ @{prefix}-center "
                    f"{{ content: {_hdr(verso_val, cnt)}; {style} }} }}"
                )
        else:
            if recto_val:
                lines.append(
                    f"@page {page_type}:right {{ @{prefix}-right "
                    f"{{ content: {_hdr(recto_val, cnt)}; {style} }} }}"
                )
            if verso_val:
                lines.append(
                    f"@page {page_type}:left {{ @{prefix}-left "
                    f"{{ content: {_hdr(verso_val, cnt)}; {style} }} }}"
                )
        return "\n".join(lines)

    css = []

    default_mt = body_mt if (has_headers or has_footers) else mt
    default_mb = body_mb if (has_headers or has_footers) else mb
    if pn and pn_start:
        css.append(f"""@page {{
  size: {pw} {ph};
  margin: {default_mt} {mo} {default_mb} {mi};
  counter-increment: pgnum;
}}""")
    else:
        css.append(f"""@page {{
  size: {pw} {ph};
  margin: {default_mt} {mo} {default_mb} {mi};
}}""")

    css.append(f"""@page :left {{
  margin-left: {mo};
  margin-right: {mi};
}}
@page :right {{
  margin-left: {mi};
  margin-right: {mo};
}}""")

    def _add_hdr_ftr(page_type: str = "", cnt: str | None = None) -> None:
        hdr_css = _margin_box_slots(
            h_recto, h_verso, h_position, "header", hdr_style, page_type, cnt
        )
        ftr_css = _margin_box_slots(
            f_recto, f_verso, f_position, "footer", ftr_style, page_type, cnt
        )
        if hdr_css:
            css.append(hdr_css)
        if ftr_css:
            css.append(ftr_css)

    if pn and not pn_start:
        _add_hdr_ftr()

    cover_extra = "counter-increment: pgnum 0;" if pn and pn_start else ""
    css.append(f"""@page cover {{
  size: {pw} {ph};
  margin: 0;
  {cover_extra}
}}""")

    if pn and pn_start:
        fm_counter_inc = "counter-increment: fmpage;" if fm_roman else "counter-increment: pgnum 0;"
        css.append(f"""@page frontmatter {{
  size: {pw} {ph};
  margin: {body_mt} {mo} {body_mb} {mi};
  {fm_counter_inc}
}}
@page frontmatter:left {{
  margin-left: {mo};
  margin-right: {mi};
}}
@page frontmatter:right {{
  margin-left: {mi};
  margin-right: {mo};
}}""")
        if fm_roman:
            _add_hdr_ftr("frontmatter", fm_counter)

        css.append(f"""@page body {{
  size: {pw} {ph};
  margin: {body_mt} {mo} {body_mb} {mi};
  counter-increment: pgnum;
}}
@page body:left {{
  margin-left: {mo};
  margin-right: {mi};
}}
@page body:right {{
  margin-left: {mi};
  margin-right: {mo};
}}""")
        _add_hdr_ftr("body")

    ta = getattr(profile, "text_align", "justify") or "justify"

    if fm_roman:
        counter_reset = "counter-reset: pgnum fmpage;"
    elif pn and pn_start:
        counter_reset = "counter-reset: pgnum;"
    else:
        counter_reset = ""
    css.append(f"""body {{
  font-family: {ff};
  font-size: {fs};
  line-height: {lh};
  color: #000;
  orphans: 2;
  widows: 2;
  text-align: {ta};
  {counter_reset}
}}""")

    ch_start_recto = getattr(profile, "chapters_start_recto", False)
    ch_page_break = "right" if ch_start_recto else "always"
    ch_ff = getattr(profile, "chapter_font_family", None) or ""
    ch_fs = getattr(profile, "chapter_font_size", None) or "1.4em"
    ch_fw = getattr(profile, "chapter_font_weight", None) or "normal"
    ch_align = getattr(profile, "chapter_align", None) or "center"
    ch_sink = getattr(profile, "chapter_sink", None)
    ch_sink_css = f"{ch_sink}em" if ch_sink is not None else "3em"
    ch_ff_css = f"font-family: {ch_ff};" if ch_ff else ""

    p_h = float(profile.page_height or 9)
    p_mt = float(profile.margin_top or 0.75)
    p_mb = float(profile.margin_bottom or 0.75)
    tp_h = f"{p_h - p_mt - p_mb}in"

    css.append(f""".cover-page {{
  page: cover;
  page-break-after: always;
}}
.cover-page img {{
  width: 100%;
  height: 100%;
  object-fit: cover;
}}
.chapter {{
  page-break-before: always;
}}
.chapter:first-of-type {{
  page-break-before: avoid;
}}
.body-chapter {{
  page-break-before: {ch_page_break};
}}
.chapter-number {{
  text-align: {ch_align};
  font-size: 1.2em;
  font-weight: {ch_fw};
  letter-spacing: 0.1em;
  text-transform: uppercase;
  margin-top: {ch_sink_css};
  margin-bottom: 0.2em;
  color: #555;
  {ch_ff_css}
}}
.chapter-title {{
  text-align: {ch_align};
  font-size: {ch_fs};
  font-weight: {ch_fw};
  margin-bottom: 2em;
  {ch_ff_css}
}}
.scene-transition {{
  break-inside: avoid;
}}
.scene-break {{
  text-align: center;
  margin: 1.5em 0;
  color: #999;
  letter-spacing: 0.5em;
}}
img {{
  max-width: 100%;
  height: auto;
}}
.full-page-image {{
  page-break-before: always;
  page-break-after: always;
  page-break-inside: avoid;
  display: table;
  width: 100%;
  height: {tp_h};
  box-sizing: border-box;
  text-align: center;
  padding: 0;
  margin: 0;
}}
.full-page-image p {{
  display: table-cell;
  vertical-align: middle;
  margin: 0;
  padding: 0;
}}
.full-page-image img {{
  max-width: 100%;
  max-height: {tp_h};
  object-fit: contain;
}}
p {{
  margin: 0.5em 0 0 0;
  text-indent: 0;
}}
p:first-child {{
  margin-top: 0;
}}
.centered-content {{
  text-align: center;
  padding-top: 30%;
}}
.centered-content p {{
  text-indent: 0;
}}
.tp-wrap {{
  position: relative;
  width: 100%;
  height: {tp_h};
  text-align: center;
  padding-top: 0;
  page-break-inside: avoid;
  page-break-after: always;
}}
.tp-content {{
  padding-top: 30%;
}}
.tp-title {{
  margin-bottom: 0.5em;
  font-weight: bold;
}}
.tp-subtitle {{
  margin-bottom: 1em;
}}
.tp-ornament {{
  margin: 1em 0;
}}
.tp-ornament img {{
  max-height: 6em;
  object-fit: contain;
}}
.tp-author {{
  margin-top: 2em;
}}
.tp-author-bottom {{
  position: absolute;
  bottom: {raw_mb}in;
  left: 0;
  right: 0;
}}""")

    if has_headers:
        css.append(""".chapter-number {
  string-set: chapter-number content();
}
.chapter-title {
  string-set: chapter-title content();
}""")

    bm_pn = getattr(profile, "back_matter_page_numbers", True)
    bm_pn = bm_pn if bm_pn is not None else True
    if pn and pn_start:
        css.append(".front-matter-chapter { page: frontmatter; }")
        if fm_roman:
            css.append(f"""@page frontmatter-nonum {{
  size: {pw} {ph};
  margin: {body_mt} {mo} {body_mb} {mi};
  {fm_counter_inc}
}}
@page frontmatter-nonum:left {{
  margin-left: {mo};
  margin-right: {mi};
}}
@page frontmatter-nonum:right {{
  margin-left: {mi};
  margin-right: {mo};
}}""")
            css.append(
                ".front-matter-chapter.centered-content "
                "{ page: frontmatter-nonum; }"
            )
        css.append(".body-chapter { page: body; }")
        if bm_pn:
            css.append(".back-matter-chapter { page: body; }")
        else:
            css.append(".back-matter-chapter { page: frontmatter; }")

    return "\n\n".join(css)


def _emulate_italic(html: str) -> str:
    """Replace font-style:italic with a skew transform for WeasyPrint.

    WeasyPrint/Pango cannot synthesize italic for custom fonts that only
    ship a Regular weight, so we use skewX(-12deg) as a visual substitute.
    """
    import re
    return re.sub(
        r'style="([^"]*?)font-style:\s*italic;?([^"]*?)"',
        r'style="\1\2 display:inline-block;transform:skewX(-12deg);"',
        html,
    )


def _build_title_page_html(work: Work) -> str | None:
    """Build structured title page HTML from work.title_page_config."""
    cfg = getattr(work, "title_page_config", None)
    if not cfg or not isinstance(cfg, dict):
        return None

    title = cfg.get("title_override") or work.title
    subtitle = cfg.get("subtitle_override") or (work.subtitle or "")
    author = cfg.get("author_override") or work.author
    author_pos = cfg.get("author_position") or "after_subtitle"
    ornament_url = cfg.get("ornament_image_url") or ""
    is_bottom = author_pos == "bottom"

    t_ff = cfg.get("title_font_family") or ""
    t_fs = cfg.get("title_font_size") or "2em"
    s_ff = cfg.get("subtitle_font_family") or ""
    s_fs = cfg.get("subtitle_font_size") or "1em"
    a_ff = cfg.get("author_font_family") or ""
    a_fs = cfg.get("author_font_size") or "1.2em"

    t_style = f"font-size:{t_fs};"
    if t_ff:
        t_style += f"font-family:{t_ff};"
    s_style = f"font-size:{s_fs};"
    if s_ff:
        s_style += f"font-family:{s_ff};"
    a_style = f"font-size:{a_fs};"
    if a_ff:
        a_style += f"font-family:{a_ff};"

    author_cls = "tp-author-bottom" if is_bottom else "tp-author"

    parts = [
        '<div class="chapter front-matter-chapter centered-content tp-wrap">',
        '<div class="tp-content">',
        f'<div class="tp-title" style="{t_style}">{_escape_html(title)}</div>',
    ]
    if subtitle:
        subtitle = _emulate_italic(subtitle)
        parts.append(f'<div class="tp-subtitle" style="{s_style}">{subtitle}</div>')
    if ornament_url:
        parts.append(f'<div class="tp-ornament"><img src="{ornament_url}" alt=""></div>')
    if not is_bottom:
        parts.append(f'<div class="{author_cls}" style="{a_style}">{_escape_html(author)}</div>')
    parts.append('</div>')
    if is_bottom:
        parts.append(f'<div class="{author_cls}" style="{a_style}">{_escape_html(author)}</div>')
    parts.append('</div>')

    return "\n".join(parts)


def _build_pdf_body(work: Work) -> str:
    """Build chapter HTML for PDF with front-matter class annotations."""
    parts: list[str] = []
    chapters = _sorted_chapters(work)
    title_page_html = _build_title_page_html(work)

    for chapter in chapters:
        if (
            title_page_html
            and chapter.title
            and chapter.title.lower().strip() == "title page"
        ):
            parts.append(title_page_html)
            continue

        if _is_front_matter(chapter.title):
            cls = "chapter front-matter-chapter"
        elif _is_back_matter(chapter.title):
            cls = "chapter back-matter-chapter"
        else:
            cls = "chapter body-chapter"
        if _is_centered(chapter.title):
            cls += " centered-content"
        chapter_parts: list[str] = [f'<div class="{cls}">']

        heading = _chapter_heading(chapter)
        if heading:
            heading_lines = heading.split("\n")
            if _is_matter(chapter.title):
                chapter_parts.append(
                    f'<div class="chapter-title">{_escape_html(heading_lines[0])}</div>'
                )
            elif len(heading_lines) == 2:
                chapter_parts.append(
                    f'<div class="chapter-number">{_escape_html(heading_lines[0])}</div>'
                )
                chapter_parts.append(
                    f'<div class="chapter-title">{_escape_html(heading_lines[1])}</div>'
                )
            else:
                chapter_parts.append(
                    f'<div class="chapter-number">{_escape_html(heading_lines[0])}</div>'
                )

        scenes = _sorted_scenes(chapter)
        scene_htmls: list[str] = []
        scene_img_only: list[bool] = []
        for scene in scenes:
            sc = (scene.content or "").strip()
            is_img = _is_image_only(sc)
            scene_img_only.append(is_img)
            if is_img and sc:
                scene_htmls.append(
                    f'<div class="full-page-image">{_md_to_html(sc)}</div>'
                )
            else:
                scene_htmls.append(_md_to_html(sc) if sc else "")
        transitions: list[str] = []
        for j in range(1, len(scene_htmls)):
            if scene_img_only[j - 1] or scene_img_only[j]:
                transitions.append("")
            else:
                prev_last, scene_htmls[j - 1] = _pop_last_block(
                    scene_htmls[j - 1]
                )
                transitions.append(
                    '<div class="scene-transition">'
                    f"{prev_last}"
                    '<div class="scene-break">***</div>'
                    "</div>"
                )
        for j, sh in enumerate(scene_htmls):
            if j > 0:
                chapter_parts.append(transitions[j - 1])
            chapter_parts.append(sh)

        chapter_parts.append("</div>")
        parts.append("\n".join(chapter_parts))

    return "\n\n".join(parts)


_BLOCK_RE = __import__("re").compile(
    r"<(p|div|blockquote|ul|ol|h[1-6])\b[^>]*>"
    r"(?:(?!<\1\b).)*?"
    r"</\1>",
    __import__("re").DOTALL,
)


def _pop_last_block(html: str) -> tuple[str, str]:
    """Remove and return the last block element from HTML."""
    blocks = list(_BLOCK_RE.finditer(html))
    if not blocks:
        return ("", html)
    last = blocks[-1]
    remaining = html[: last.start()].rstrip()
    tail = html[last.end():]
    if tail.strip():
        remaining += tail
        return (last.group(0), remaining)
    return (last.group(0), remaining)


def _build_font_face_css(fonts: list) -> str:
    """Generate @font-face CSS rules for uploaded custom fonts."""
    rules: list[str] = []
    for font in fonts:
        ext = Path(font.filename).suffix.lower()
        fmt_map = {".ttf": "truetype", ".otf": "opentype", ".woff": "woff", ".woff2": "woff2"}
        fmt = fmt_map.get(ext, "truetype")
        font_path = UPLOAD_DIR / "fonts" / font.filename
        if font_path.exists():
            uri = font_path.as_uri()
            rules.append(
                f"@font-face {{ font-family: '{font.family_name}'; "
                f"src: url('{uri}') format('{fmt}'); }}"
            )
            rules.append(
                f"@font-face {{ font-family: '{font.family_name}'; "
                f"font-weight: bold; "
                f"src: url('{uri}') format('{fmt}'); }}"
            )
    return "\n".join(rules)


def _build_pdf_html(work: Work, profile: Profile, fonts: list | None = None) -> str:
    """Build the full HTML document for PDF rendering."""
    font_face_css = _build_font_face_css(fonts or [])
    css = _build_pdf_css(profile, work)
    body = _build_pdf_body(work)

    cover_html = ""
    if profile.include_cover and work.cover_image_path:
        cover_file = UPLOAD_DIR / work.cover_image_path.removeprefix("/uploads/")
        if cover_file.exists():
            cover_uri = cover_file.as_uri()
            cover_html = (
                f'<div class="cover-page">'
                f'<img src="{cover_uri}" alt="Cover">'
                f"</div>"
            )

    body = _resolve_image_paths(body)

    return f"""<!DOCTYPE html>
<html lang="{work.language or 'en'}">
<head>
<meta charset="utf-8">
<title>{_escape_html(work.title)}</title>
<style>
{font_face_css}
{css}
</style>
</head>
<body>
{cover_html}
{body}
</body>
</html>"""


def _resolve_image_paths(html: str) -> str:
    """Replace /uploads/... src attributes with local file:// URIs for WeasyPrint."""
    import re

    def _replace(match: re.Match) -> str:
        src = match.group(1)
        if src.startswith("/uploads/"):
            local_path = UPLOAD_DIR / src[len("/uploads/"):]
            if local_path.exists():
                return f'src="{local_path.as_uri()}"'
        return match.group(0)

    return re.sub(r'src="(/uploads/[^"]*)"', _replace, html)


async def export_pdf(
    db: AsyncSession, work_id: uuid.UUID, profile_id: uuid.UUID | None = None
) -> tuple[bytes, str]:
    """Return (pdf_bytes, suggested_filename)."""
    import weasyprint

    work = await _load_work(db, work_id)

    profile: Profile | None = None
    if profile_id:
        profile = await _load_profile(db, profile_id)
    elif work.default_profile_id:
        p = await db.get(Profile, work.default_profile_id)
        if p and p.format == "pdf":
            profile = p

    if profile is None:
        profile = Profile(
            name="Default",
            format="pdf",
            page_width=6.0,
            page_height=9.0,
            margin_top=0.75,
            margin_bottom=0.75,
            margin_inner=0.875,
            margin_outer=0.625,
            font_family="Georgia, serif",
            font_size="11pt",
            line_height=1.5,
            header_footer=False,
            include_cover=True,
            include_toc=False,
            page_numbers=False,
            page_number_position="center",
            page_numbers_start_at_content=True,
        )

    from app.models.font import Font as FontModel

    font_result = await db.execute(select(FontModel))
    fonts = list(font_result.scalars().all())

    html_str = _build_pdf_html(work, profile, fonts)

    # Render to PDF bytes
    html_doc = weasyprint.HTML(string=html_str, base_url=str(UPLOAD_DIR))
    pdf_bytes = html_doc.write_pdf()

    filename = _safe_filename(work.title) + ".pdf"
    return pdf_bytes, filename


# ---------------------------------------------------------------------------
# ePub export (ebooklib)
# ---------------------------------------------------------------------------


def _epub_css(profile: Profile) -> str:
    ff = profile.font_family or "Georgia, serif"
    fs = profile.font_size or "1em"
    lh = profile.line_height or 1.5
    return f"""body {{
  font-family: {ff};
  font-size: {fs};
  line-height: {lh};
  color: #000;
}}
.chapter-number {{
  text-align: center;
  font-size: 1.2em;
  letter-spacing: 0.1em;
  text-transform: uppercase;
  margin-bottom: 0.2em;
  color: #555;
}}
.chapter-title {{
  text-align: center;
  font-size: 1.4em;
  margin-bottom: 2em;
}}
.scene-break {{
  text-align: center;
  margin: 1.5em 0;
  color: #999;
  letter-spacing: 0.5em;
  break-before: avoid;
  break-after: avoid;
  break-inside: avoid;
}}
img {{
  max-width: 100%;
  height: auto;
}}
.full-page-image {{
  page-break-before: always;
  page-break-after: always;
  page-break-inside: avoid;
  display: flex;
  align-items: center;
  justify-content: center;
  height: 100vh;
  box-sizing: border-box;
}}
.full-page-image img {{
  max-width: 100%;
  max-height: 100%;
  object-fit: contain;
}}
p {{
  margin: 0.5em 0 0 0;
  text-indent: 0;
}}
p:first-child {{
  margin-top: 0;
}}
.centered-content {{
  text-align: center;
}}
.centered-content p {{
  text-indent: 0;
}}"""


async def export_epub(
    db: AsyncSession,
    work_id: uuid.UUID,
    profile_id: uuid.UUID | None = None,
    compress_images: bool = False,
) -> tuple[bytes, str]:
    """Return (epub_bytes, suggested_filename)."""
    import io

    from ebooklib import epub

    work = await _load_work(db, work_id)

    profile: Profile | None = None
    if profile_id:
        profile = await _load_profile(db, profile_id)
    elif work.default_profile_id:
        p = await db.get(Profile, work.default_profile_id)
        if p and p.format == "epub":
            profile = p

    if profile is None:
        profile = Profile(
            name="Default",
            format="epub",
            font_family="Georgia, serif",
            font_size="1em",
            line_height=1.5,
            include_cover=True,
            include_toc=True,
        )

    book = epub.EpubBook()
    book.set_identifier(str(work_id))
    book.set_title(work.title)
    book.set_language(work.language or "en")
    if work.author:
        book.add_author(work.author)

    style = epub.EpubItem(
        uid="style",
        file_name="style/default.css",
        media_type="text/css",
        content=_epub_css(profile).encode("utf-8"),
    )
    book.add_item(style)

    # Cover image
    if profile.include_cover and work.cover_image_path:
        cover_file = UPLOAD_DIR / work.cover_image_path.removeprefix("/uploads/")
        if cover_file.exists():
            cover_data = cover_file.read_bytes()
            if compress_images:
                cover_data = _compress_image_bytes(cover_data, max_width=1600)
            ext = ".jpg" if compress_images else cover_file.suffix.lower()
            book.set_cover("cover" + ext, cover_data, create_page=True)

    # Collect inline images used in scene content
    inline_images: dict[str, epub.EpubItem] = {}

    chapters_sorted = _sorted_chapters(work)
    epub_chapters: list[epub.EpubHtml] = []
    spine: list = ["nav"] if profile.include_toc else []
    toc: list = []

    for idx, chapter in enumerate(chapters_sorted):
        heading = _chapter_heading(chapter)
        heading_html = ""
        toc_title = chapter.title or f"Chapter {chapter.number or idx + 1}"

        if heading:
            heading_lines = heading.split("\n")
            if _is_matter(chapter.title):
                heading_html = (
                    f'<div class="chapter-title">{_escape_html(heading_lines[0])}</div>'
                )
            elif len(heading_lines) == 2:
                heading_html = (
                    f'<div class="chapter-number">{_escape_html(heading_lines[0])}</div>'
                    f'<div class="chapter-title">{_escape_html(heading_lines[1])}</div>'
                )
            else:
                heading_html = (
                    f'<div class="chapter-number">{_escape_html(heading_lines[0])}</div>'
                )

        scenes = _sorted_scenes(chapter)
        content_parts: list[str] = []
        for j, scene in enumerate(scenes):
            scene_content = (scene.content or "").strip()
            is_img = _is_image_only(scene_content)
            prev_img = j > 0 and _is_image_only(scenes[j - 1].content)
            if j > 0 and not prev_img and not is_img:
                content_parts.append('<div class="scene-break">***</div>')
            if scene_content:
                html_content = _md_to_html(scene_content)
                html_content = _collect_epub_images(
                    html_content, inline_images, book,
                    compress=compress_images,
                )
                if is_img:
                    html_content = f'<div class="full-page-image">{html_content}</div>'
                content_parts.append(html_content)

        ch_cls = (
            "chapter centered-content"
            if _is_centered(chapter.title)
            else "chapter"
        )
        body_html = (
            f'<div class="{ch_cls}">{heading_html}'
            f'{"".join(content_parts)}</div>'
        )
        full_html = (
            '<?xml version="1.0" encoding="utf-8"?>'
            "<!DOCTYPE html>"
            '<html xmlns="http://www.w3.org/1999/xhtml">'
            "<head>"
            f"<title>{_escape_html(toc_title)}</title>"
            '<link rel="stylesheet" href="style/default.css" type="text/css"/>'
            "</head>"
            f"<body>{body_html}</body></html>"
        )

        ch_item = epub.EpubHtml(
            title=toc_title,
            file_name=f"chapter_{idx:03d}.xhtml",
            lang=work.language or "en",
        )
        ch_item.set_content(full_html.encode("utf-8"))
        ch_item.add_item(style)
        book.add_item(ch_item)
        epub_chapters.append(ch_item)
        spine.append(ch_item)
        toc.append(ch_item)

    book.toc = toc
    book.spine = spine
    book.add_item(epub.EpubNcx())
    book.add_item(epub.EpubNav())

    buf = io.BytesIO()
    epub.write_epub(buf, book)
    buf.seek(0)
    filename = _safe_filename(work.title) + ".epub"
    return buf.read(), filename


def _collect_epub_images(
    html: str, images: dict, book: object, *, compress: bool = False
) -> str:
    """Replace /uploads/ image paths with epub-relative paths and register images."""
    import re

    from ebooklib import epub

    def _replace(match: re.Match) -> str:
        src = match.group(1)
        if not src.startswith("/uploads/"):
            return match.group(0)
        if src in images:
            return f'src="{images[src].file_name}"'
        local_path = UPLOAD_DIR / src[len("/uploads/"):]
        if not local_path.exists():
            return match.group(0)

        if compress:
            content = _compress_image_bytes(local_path.read_bytes())
            stem = local_path.stem
            fname = f"images/{stem}.jpg"
            media = "image/jpeg"
        else:
            ext = local_path.suffix.lower()
            media = {
                ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
                ".png": "image/png", ".webp": "image/webp",
                ".gif": "image/gif",
            }.get(ext, "image/jpeg")
            fname = f"images/{local_path.name}"
            content = local_path.read_bytes()

        item = epub.EpubImage(
            uid=f"img_{len(images)}",
            file_name=fname,
            media_type=media,
            content=content,
        )
        book.add_item(item)
        images[src] = item
        return f'src="{fname}"'

    return re.sub(r'src="(/uploads/[^"]*)"', _replace, html)


# ---------------------------------------------------------------------------
# DOCX export (python-docx)
# ---------------------------------------------------------------------------


def _parse_font_size(size_str: str | None) -> float | None:
    """Parse a CSS-style font size string to points."""
    if not size_str:
        return None
    import re
    m = re.match(r"([\d.]+)\s*(pt|px|em|rem)?", size_str.strip())
    if not m:
        return None
    val = float(m.group(1))
    unit = m.group(2) or "pt"
    if unit == "pt":
        return val
    if unit == "px":
        return val * 0.75
    if unit in ("em", "rem"):
        return val * 11
    return val


def _docx_add_scene_content(doc, scene_content: str, font_name: str, font_size_pt: float):
    """Add scene markdown content to the document as paragraphs."""
    import re

    from docx.shared import Inches

    if not scene_content.strip():
        return

    lines = scene_content.split("\n")
    para_lines: list[str] = []

    def flush_paragraph():
        nonlocal para_lines
        if not para_lines:
            return
        text = " ".join(para_lines)
        _docx_add_rich_paragraph(doc, text, font_name, font_size_pt)
        para_lines = []

    for line in lines:
        stripped = line.strip()

        if not stripped:
            flush_paragraph()
            continue

        if re.match(r"^!\[([^\]]*)\]\(([^)]*)\)$", stripped):
            flush_paragraph()
            m = re.match(r"^!\[([^\]]*)\]\(([^)]*)\)$", stripped)
            if m:
                img_path = m.group(2)
                if img_path.startswith("/uploads/"):
                    local = UPLOAD_DIR / img_path[len("/uploads/"):]
                    if local.exists():
                        p = doc.add_paragraph()
                        p.alignment = 1  # center
                        run = p.add_run()
                        run.add_picture(str(local), width=Inches(4.0))
            continue

        para_lines.append(stripped)

    flush_paragraph()


def _docx_add_rich_paragraph(doc, text: str, font_name: str, font_size_pt: float):
    """Add a paragraph with basic markdown bold/italic formatting."""
    import re

    from docx.shared import Pt

    p = doc.add_paragraph()
    fmt = p.paragraph_format
    fmt.space_before = Pt(0)
    fmt.space_after = Pt(font_size_pt * 0.45)

    bold_italic_re = re.compile(r"\*\*\*(.+?)\*\*\*|___(.+?)___")
    bold_re = re.compile(r"\*\*(.+?)\*\*|__(.+?)__")
    italic_re = re.compile(r"\*(.+?)\*|_(.+?)_")
    image_inline_re = re.compile(r"!\[([^\]]*)\]\([^)]*\)")

    text = image_inline_re.sub(r"[\1]", text)
    link_re = re.compile(r"\[([^\]]*)\]\([^)]*\)")
    text = link_re.sub(r"\1", text)

    tokens = re.split(r"(\*{1,3}[^*]+\*{1,3}|_{1,3}[^_]+_{1,3})", text)

    for token in tokens:
        if not token:
            continue
        m = bold_italic_re.fullmatch(token)
        if m:
            run = p.add_run(m.group(1) or m.group(2))
            run.bold = True
            run.italic = True
            run.font.name = font_name
            run.font.size = Pt(font_size_pt)
            continue
        m = bold_re.fullmatch(token)
        if m:
            run = p.add_run(m.group(1) or m.group(2))
            run.bold = True
            run.font.name = font_name
            run.font.size = Pt(font_size_pt)
            continue
        m = italic_re.fullmatch(token)
        if m:
            run = p.add_run(m.group(1) or m.group(2))
            run.italic = True
            run.font.name = font_name
            run.font.size = Pt(font_size_pt)
            continue
        run = p.add_run(token)
        run.font.name = font_name
        run.font.size = Pt(font_size_pt)


def _build_docx(work: Work, profile: Profile) -> bytes:
    """Build a DOCX document from a work using profile settings."""
    import io

    from docx import Document
    from docx.enum.text import WD_ALIGN_PARAGRAPH
    from docx.shared import Inches, Pt, RGBColor

    doc = Document()

    pw = float(profile.page_width or 6.0)
    ph = float(profile.page_height or 9.0)
    mt = float(profile.margin_top or 0.75)
    mb = float(profile.margin_bottom or 0.75)
    mi = float(profile.margin_inner or 0.875)
    mo = float(profile.margin_outer or 0.625)
    ff = (profile.font_family or "Georgia, serif").split(",")[0].strip().strip("'\"")
    fs = _parse_font_size(profile.font_size) or 11.0
    lh = float(profile.line_height or 1.5)

    ch_ff = (getattr(profile, "chapter_font_family", None) or ff).split(",")[0].strip().strip("'\"")
    ch_fs = _parse_font_size(getattr(profile, "chapter_font_size", None)) or 18.0
    ch_fw = getattr(profile, "chapter_font_weight", None) or "bold"
    ch_align_str = getattr(profile, "chapter_align", None) or "center"
    raw_sink = getattr(profile, "chapter_sink", None)
    ch_sink = float(raw_sink) if raw_sink else None

    align_map = {
        "center": WD_ALIGN_PARAGRAPH.CENTER,
        "left": WD_ALIGN_PARAGRAPH.LEFT,
        "right": WD_ALIGN_PARAGRAPH.RIGHT,
        "justify": WD_ALIGN_PARAGRAPH.JUSTIFY,
    }
    ch_align = align_map.get(ch_align_str, WD_ALIGN_PARAGRAPH.CENTER)
    text_align = align_map.get(
        getattr(profile, "text_align", "justify") or "justify",
        WD_ALIGN_PARAGRAPH.JUSTIFY,
    )

    section = doc.sections[0]
    section.page_width = Inches(pw)
    section.page_height = Inches(ph)
    section.top_margin = Inches(mt)
    section.bottom_margin = Inches(mb)
    section.left_margin = Inches(mi)
    section.right_margin = Inches(mo)

    style = doc.styles["Normal"]
    style.font.name = ff
    style.font.size = Pt(fs)
    style.paragraph_format.line_spacing = lh
    style.paragraph_format.alignment = text_align

    chapters = _sorted_chapters(work)
    cfg = getattr(work, "title_page_config", None)
    has_title_page_config = cfg and isinstance(cfg, dict)

    for ch_idx, chapter in enumerate(chapters):
        is_title_page = (
            chapter.title
            and chapter.title.lower().strip() == "title page"
        )

        if ch_idx > 0:
            doc.add_section()
            new_section = doc.sections[-1]
            new_section.page_width = Inches(pw)
            new_section.page_height = Inches(ph)
            new_section.top_margin = Inches(mt)
            new_section.bottom_margin = Inches(mb)
            new_section.left_margin = Inches(mi)
            new_section.right_margin = Inches(mo)

        if is_title_page and has_title_page_config:
            _docx_add_title_page(doc, work, cfg, ch_ff, ch_fs, ff, fs, ch_sink)
            continue

        if ch_sink and ch_sink > 0:
            spacer = doc.add_paragraph()
            spacer.paragraph_format.space_before = Pt(ch_sink)
            spacer.paragraph_format.space_after = Pt(0)

        heading = _chapter_heading(chapter)
        if heading:
            heading_lines = heading.split("\n")
            if _is_matter(chapter.title):
                p = doc.add_paragraph()
                p.alignment = ch_align
                run = p.add_run(heading_lines[0])
                run.font.name = ch_ff
                run.font.size = Pt(ch_fs)
                run.bold = ch_fw == "bold"
            elif len(heading_lines) == 2:
                p = doc.add_paragraph()
                p.alignment = ch_align
                run = p.add_run(heading_lines[0])
                run.font.name = ch_ff
                run.font.size = Pt(ch_fs * 0.7)
                run.font.color.rgb = RGBColor(0x55, 0x55, 0x55)

                p2 = doc.add_paragraph()
                p2.alignment = ch_align
                run2 = p2.add_run(heading_lines[1])
                run2.font.name = ch_ff
                run2.font.size = Pt(ch_fs)
                run2.bold = ch_fw == "bold"
            else:
                p = doc.add_paragraph()
                p.alignment = ch_align
                run = p.add_run(heading_lines[0])
                run.font.name = ch_ff
                run.font.size = Pt(ch_fs * 0.7)
                run.font.color.rgb = RGBColor(0x55, 0x55, 0x55)

        p_space = doc.add_paragraph()
        p_space.paragraph_format.space_before = Pt(18)
        p_space.paragraph_format.space_after = Pt(0)

        is_centered = _is_centered(chapter.title)

        scenes = _sorted_scenes(chapter)
        for s_idx, scene in enumerate(scenes):
            content = (scene.content or "").strip()
            is_img = _is_image_only(content)
            prev_img = s_idx > 0 and _is_image_only(scenes[s_idx - 1].content)
            if s_idx > 0 and not prev_img and not is_img:
                brk = doc.add_paragraph()
                brk.alignment = WD_ALIGN_PARAGRAPH.CENTER
                brk.paragraph_format.space_before = Pt(12)
                brk.paragraph_format.space_after = Pt(12)
                run = brk.add_run("***")
                run.font.name = ff
                run.font.size = Pt(fs)
                run.font.color.rgb = RGBColor(0x99, 0x99, 0x99)

            if is_img and content:
                m = re.match(r"^!\[([^\]]*)\]\(([^)]+)\)", content)
                if m:
                    img_path = m.group(2)
                    if img_path.startswith("/uploads/"):
                        local = UPLOAD_DIR / img_path[len("/uploads/"):]
                        if local.exists():
                            p = doc.add_paragraph()
                            p.alignment = WD_ALIGN_PARAGRAPH.CENTER
                            p.paragraph_format.page_break_before = True
                            run = p.add_run()
                            max_w = Inches(pw - mi - mo)
                            max_h = Inches(ph - mt - mb)
                            from PIL import Image as PILImage
                            with PILImage.open(str(local)) as pil_img:
                                iw, ih = pil_img.size
                            aspect = iw / ih
                            if max_w / max_h > aspect:
                                run.add_picture(str(local), height=max_h)
                            else:
                                run.add_picture(str(local), width=max_w)
            elif content:
                _docx_add_scene_content(doc, content, ff, fs)

        if is_centered:
            for para in doc.paragraphs:
                pass

    # Cover image on first page
    if profile.include_cover and work.cover_image_path:
        cover_file = UPLOAD_DIR / work.cover_image_path.removeprefix("/uploads/")
        if cover_file.exists():
            cover_section = doc.sections[0]
            cover_section.top_margin = Inches(0)
            cover_section.bottom_margin = Inches(0)
            cover_section.left_margin = Inches(0)
            cover_section.right_margin = Inches(0)

            first_para = doc.paragraphs[0] if doc.paragraphs else doc.add_paragraph()
            first_para.clear()
            first_para.alignment = WD_ALIGN_PARAGRAPH.CENTER
            run = first_para.add_run()
            run.add_picture(str(cover_file), width=Inches(pw))

            doc.add_section()
            new_section = doc.sections[-1]
            new_section.page_width = Inches(pw)
            new_section.page_height = Inches(ph)
            new_section.top_margin = Inches(mt)
            new_section.bottom_margin = Inches(mb)
            new_section.left_margin = Inches(mi)
            new_section.right_margin = Inches(mo)

    buf = io.BytesIO()
    doc.save(buf)
    buf.seek(0)
    return buf.read()


def _docx_add_title_page(
    doc, work: Work, cfg: dict,
    ch_ff: str, ch_fs: float, body_ff: str, body_fs: float,
    ch_sink: float | None,
):
    """Add a structured title page to the DOCX document."""
    from docx.enum.text import WD_ALIGN_PARAGRAPH
    from docx.shared import Pt

    title = cfg.get("title_override") or work.title
    subtitle = cfg.get("subtitle_override") or (work.subtitle or "")
    author = cfg.get("author_override") or work.author
    author_pos = cfg.get("author_position") or "after_subtitle"

    t_ff = (cfg.get("title_font_family") or ch_ff).split(",")[0].strip().strip("'\"")
    t_fs = _parse_font_size(cfg.get("title_font_size")) or ch_fs
    s_ff = (cfg.get("subtitle_font_family") or body_ff).split(",")[0].strip().strip("'\"")
    s_fs = _parse_font_size(cfg.get("subtitle_font_size")) or body_fs
    a_ff = (cfg.get("author_font_family") or body_ff).split(",")[0].strip().strip("'\"")
    a_fs = _parse_font_size(cfg.get("author_font_size")) or body_fs * 1.1

    if ch_sink and ch_sink > 0:
        spacer = doc.add_paragraph()
        spacer.paragraph_format.space_before = Pt(ch_sink)

    p_title = doc.add_paragraph()
    p_title.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = p_title.add_run(title)
    run.font.name = t_ff
    run.font.size = Pt(t_fs)

    import re
    clean_subtitle = re.sub(r"<[^>]+>", "", subtitle).strip()
    if clean_subtitle:
        p_sub = doc.add_paragraph()
        p_sub.alignment = WD_ALIGN_PARAGRAPH.CENTER
        run = p_sub.add_run(clean_subtitle)
        run.font.name = s_ff
        run.font.size = Pt(s_fs)

    if author_pos != "bottom":
        p_auth = doc.add_paragraph()
        p_auth.alignment = WD_ALIGN_PARAGRAPH.CENTER
        p_auth.paragraph_format.space_before = Pt(24)
        run = p_auth.add_run(author)
        run.font.name = a_ff
        run.font.size = Pt(a_fs)
    else:
        for _ in range(8):
            doc.add_paragraph()
        p_auth = doc.add_paragraph()
        p_auth.alignment = WD_ALIGN_PARAGRAPH.CENTER
        run = p_auth.add_run(author)
        run.font.name = a_ff
        run.font.size = Pt(a_fs)


async def export_docx(
    db: AsyncSession, work_id: uuid.UUID, profile_id: uuid.UUID | None = None
) -> tuple[bytes, str]:
    """Return (docx_bytes, suggested_filename)."""
    work = await _load_work(db, work_id)

    profile: Profile | None = None
    if profile_id:
        profile = await _load_profile(db, profile_id)
    elif work.default_profile_id:
        p = await db.get(Profile, work.default_profile_id)
        if p and p.format == "pdf":
            profile = p

    if profile is None:
        profile = Profile(
            name="Default",
            format="pdf",
            page_width=6.0,
            page_height=9.0,
            margin_top=0.75,
            margin_bottom=0.75,
            margin_inner=0.875,
            margin_outer=0.625,
            font_family="Georgia, serif",
            font_size="11pt",
            line_height=1.5,
            header_footer=False,
            include_cover=True,
            include_toc=False,
            page_numbers=False,
            page_number_position="center",
            page_numbers_start_at_content=True,
        )

    docx_bytes = _build_docx(work, profile)
    filename = _safe_filename(work.title) + ".docx"
    return docx_bytes, filename


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _escape_html(text: str) -> str:
    """Escape HTML special characters."""
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def _safe_filename(title: str) -> str:
    """Convert a work title into a safe filename."""
    import re

    name = re.sub(r"[^\w\s-]", "", title).strip()
    name = re.sub(r"[\s]+", "_", name)
    return name or "export"


class ExportError(Exception):
    pass


class WorkNotFoundError(ExportError):
    def __init__(self, work_id: uuid.UUID):
        super().__init__(f"Work not found: {work_id}")
        self.work_id = work_id


class ProfileNotFoundError(ExportError):
    def __init__(self, profile_id: uuid.UUID):
        super().__init__(f"Profile not found: {profile_id}")
        self.profile_id = profile_id
