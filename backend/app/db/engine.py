from __future__ import annotations

from collections.abc import AsyncGenerator

from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.config import settings
from app.db.base import Base

engine = create_async_engine(settings.DATABASE_URL, echo=False)


@event.listens_for(engine.sync_engine, "connect")
def _set_sqlite_pragma(dbapi_connection, connection_record):
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()


async_session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with async_session_factory() as session:
        yield session


async def init_db() -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        await conn.execute(
            __import__("sqlalchemy").text(
                "ALTER TABLE profiles ADD COLUMN header_recto VARCHAR(50)"
            )
        ) if await _column_missing(conn, "profiles", "header_recto") else None
        await conn.execute(
            __import__("sqlalchemy").text(
                "ALTER TABLE profiles ADD COLUMN header_verso VARCHAR(50)"
            )
        ) if await _column_missing(conn, "profiles", "header_verso") else None
        await conn.execute(
            __import__("sqlalchemy").text(
                "ALTER TABLE profiles ADD COLUMN header_position VARCHAR(20) DEFAULT 'outer'"
            )
        ) if await _column_missing(conn, "profiles", "header_position") else None
        for col, sql in [
            ("text_align", "ALTER TABLE profiles ADD COLUMN text_align VARCHAR(20) DEFAULT 'justify'"),
            ("chapter_font_family", "ALTER TABLE profiles ADD COLUMN chapter_font_family VARCHAR(200)"),
            ("chapter_font_size", "ALTER TABLE profiles ADD COLUMN chapter_font_size VARCHAR(20)"),
            ("chapter_font_weight", "ALTER TABLE profiles ADD COLUMN chapter_font_weight VARCHAR(20)"),
            ("chapter_align", "ALTER TABLE profiles ADD COLUMN chapter_align VARCHAR(20)"),
            ("chapter_sink", "ALTER TABLE profiles ADD COLUMN chapter_sink FLOAT"),
            ("chapters_start_recto", "ALTER TABLE profiles ADD COLUMN chapters_start_recto BOOLEAN DEFAULT 0"),
            ("header_font_family", "ALTER TABLE profiles ADD COLUMN header_font_family VARCHAR(200)"),
            ("header_font_size", "ALTER TABLE profiles ADD COLUMN header_font_size VARCHAR(20)"),
            ("header_margin_top", "ALTER TABLE profiles ADD COLUMN header_margin_top FLOAT"),
            ("header_from_edge", "ALTER TABLE profiles ADD COLUMN header_from_edge FLOAT"),
            ("footer_margin_bottom", "ALTER TABLE profiles ADD COLUMN footer_margin_bottom FLOAT"),
            ("footer_from_edge", "ALTER TABLE profiles ADD COLUMN footer_from_edge FLOAT"),
            ("back_matter_page_numbers", "ALTER TABLE profiles ADD COLUMN back_matter_page_numbers BOOLEAN DEFAULT 1"),
            ("footer_recto", "ALTER TABLE profiles ADD COLUMN footer_recto VARCHAR(50)"),
            ("footer_verso", "ALTER TABLE profiles ADD COLUMN footer_verso VARCHAR(50)"),
            ("footer_position", "ALTER TABLE profiles ADD COLUMN footer_position VARCHAR(20) DEFAULT 'center'"),
            ("header_font_weight", "ALTER TABLE profiles ADD COLUMN header_font_weight VARCHAR(20)"),
            ("front_matter_roman", "ALTER TABLE profiles ADD COLUMN front_matter_roman BOOLEAN DEFAULT 0"),
        ]:
            if await _column_missing(conn, "profiles", col):
                await conn.execute(__import__("sqlalchemy").text(sql))
        # Migrate page_numbers to footer content
        await conn.execute(
            __import__("sqlalchemy").text(
                "UPDATE profiles SET footer_recto = 'page_number', footer_verso = 'page_number', "
                "footer_position = CASE WHEN page_number_position = 'outside' THEN 'outer' "
                "WHEN page_number_position = 'center' THEN 'center' ELSE 'center' END "
                "WHERE page_numbers = 1 AND footer_recto IS NULL"
            )
        )
        await conn.execute(
            __import__("sqlalchemy").text(
                "ALTER TABLE works ADD COLUMN ai_instructions TEXT DEFAULT ''"
            )
        ) if await _column_missing(conn, "works", "ai_instructions") else None
        await conn.execute(
            __import__("sqlalchemy").text(
                "ALTER TABLE series ADD COLUMN ai_instructions TEXT DEFAULT ''"
            )
        ) if await _column_missing(conn, "series", "ai_instructions") else None
        if await _column_missing(conn, "comments", "suggestion"):
            await conn.execute(
                __import__("sqlalchemy").text(
                    "ALTER TABLE comments ADD COLUMN suggestion TEXT"
                )
            )
        if await _column_missing(conn, "scenes", "checkpoint"):
            await conn.execute(
                __import__("sqlalchemy").text(
                    "ALTER TABLE scenes ADD COLUMN checkpoint TEXT"
                )
            )
        if await _column_missing(conn, "works", "title_page_config"):
            await conn.execute(
                __import__("sqlalchemy").text(
                    "ALTER TABLE works ADD COLUMN title_page_config TEXT"
                )
            )
        if await _column_missing(conn, "codex_entries", "voice_id"):
            await conn.execute(
                __import__("sqlalchemy").text(
                    "ALTER TABLE codex_entries ADD COLUMN voice_id VARCHAR(100)"
                )
            )
        if await _column_missing(conn, "images", "tags"):
            await conn.execute(
                __import__("sqlalchemy").text(
                    "ALTER TABLE images ADD COLUMN tags TEXT DEFAULT ''"
                )
            )
        from sqlalchemy import text
        for name, mt, mb, hmt, hfe, fmb, ffe, fr, fv, fp in [
            ("Paperback 6x9", 0.875, 0.875, 0.25, 0.3, 0.25, 0.3, "page_number", "page_number", "outer"),
            ("Paperback 5.5x8.5", 0.8, 0.8, 0.2, 0.3, 0.2, 0.3, "page_number", "page_number", "center"),
            ("Hardback 6x9", 1.0, 1.0, 0.3, 0.35, 0.3, 0.35, "page_number", "page_number", "outer"),
        ]:
            await conn.execute(text(
                "UPDATE profiles SET margin_top = :mt, margin_bottom = :mb, "
                "header_margin_top = :hmt, header_from_edge = :hfe, "
                "footer_margin_bottom = :fmb, footer_from_edge = :ffe, "
                "footer_recto = :fr, footer_verso = :fv, footer_position = :fp "
                "WHERE name = :name AND is_builtin = 1"
            ), {"mt": mt, "mb": mb, "hmt": hmt, "hfe": hfe, "fmb": fmb, "ffe": ffe,
                "fr": fr, "fv": fv, "fp": fp, "name": name})
        # User ownership columns
        for table, col in [
            ("series", "user_id"),
            ("works", "user_id"),
            ("conversations", "user_id"),
        ]:
            if await _column_missing(conn, table, col):
                await conn.execute(text(
                    f"ALTER TABLE {table} ADD COLUMN {col} VARCHAR(36)"
                ))
    await _seed_profiles()
    await _backfill_user_ownership()


async def _column_missing(conn, table: str, column: str) -> bool:
    from sqlalchemy import text

    result = await conn.execute(text(f"PRAGMA table_info({table})"))
    columns = [row[1] for row in result.fetchall()]
    return column not in columns


async def _seed_profiles() -> None:
    from sqlalchemy import select

    from app.models.profile import Profile, ProfileFormat

    builtin = [
        {
            "name": "Standard ePub",
            "format": ProfileFormat.EPUB,
            "description": "Default ebook format for e-readers",
            "is_builtin": True,
            "font_family": "Georgia, serif",
            "font_size": "1em",
            "line_height": 1.5,
            "include_cover": True,
            "include_toc": True,
        },
        {
            "name": "Paperback 6x9",
            "format": ProfileFormat.PDF,
            "description": "Standard trade paperback",
            "is_builtin": True,
            "page_width": 6.0,
            "page_height": 9.0,
            "margin_top": 0.875,
            "margin_bottom": 0.875,
            "margin_inner": 0.875,
            "margin_outer": 0.625,
            "header_margin_top": 0.25,
            "header_from_edge": 0.3,
            "footer_margin_bottom": 0.25,
            "footer_from_edge": 0.3,
            "font_family": "Garamond, serif",
            "font_size": "11pt",
            "line_height": 1.5,
            "include_cover": True,
            "page_numbers": True,
            "page_number_position": "outside",
            "page_numbers_start_at_content": True,
            "header_recto": "author",
            "header_verso": "title",
            "header_position": "outer",
            "footer_recto": "page_number",
            "footer_verso": "page_number",
            "footer_position": "outer",
        },
        {
            "name": "Paperback 5.5x8.5",
            "format": ProfileFormat.PDF,
            "description": "Digest-size paperback (B&N Press, KDP)",
            "is_builtin": True,
            "page_width": 5.5,
            "page_height": 8.5,
            "margin_top": 0.8,
            "margin_bottom": 0.8,
            "margin_inner": 0.75,
            "margin_outer": 0.5,
            "header_margin_top": 0.2,
            "header_from_edge": 0.3,
            "footer_margin_bottom": 0.2,
            "footer_from_edge": 0.3,
            "font_family": "Garamond, serif",
            "font_size": "11pt",
            "line_height": 1.4,
            "include_cover": True,
            "page_numbers": True,
            "page_number_position": "center",
            "page_numbers_start_at_content": True,
            "header_recto": "author",
            "header_verso": "title",
            "header_position": "center",
            "footer_recto": "page_number",
            "footer_verso": "page_number",
            "footer_position": "center",
        },
        {
            "name": "Hardback 6x9",
            "format": ProfileFormat.PDF,
            "description": "Standard hardcover",
            "is_builtin": True,
            "page_width": 6.0,
            "page_height": 9.0,
            "margin_top": 1.0,
            "margin_bottom": 1.0,
            "margin_inner": 1.0,
            "margin_outer": 0.75,
            "header_margin_top": 0.3,
            "header_from_edge": 0.35,
            "footer_margin_bottom": 0.3,
            "footer_from_edge": 0.35,
            "font_family": "Garamond, serif",
            "font_size": "12pt",
            "line_height": 1.5,
            "include_cover": True,
            "page_numbers": True,
            "page_number_position": "outside",
            "page_numbers_start_at_content": True,
            "header_recto": "author",
            "header_verso": "title",
            "header_position": "outer",
            "footer_recto": "page_number",
            "footer_verso": "page_number",
            "footer_position": "outer",
        },
    ]

    async with async_session_factory() as session:
        result = await session.execute(
            select(Profile).where(Profile.is_builtin.is_(True))
        )
        existing = {p.name for p in result.scalars().all()}
        for profile_data in builtin:
            if profile_data["name"] not in existing:
                session.add(Profile(**profile_data))
        await session.commit()


async def _backfill_user_ownership() -> None:
    """Assign unowned records to the local user if in local auth mode."""
    from sqlalchemy import text

    from app.services.auth import AUTH_MODE, get_or_create_local_user

    if AUTH_MODE != "local":
        return

    async with async_session_factory() as session:
        user = await get_or_create_local_user(session)
        uid = user.id.hex
        for table in ("series", "works", "conversations"):
            await session.execute(
                text(f"UPDATE {table} SET user_id = :uid WHERE user_id IS NULL"),
                {"uid": uid},
            )
        await session.commit()
