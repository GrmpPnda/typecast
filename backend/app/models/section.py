from __future__ import annotations

import enum
import uuid

from sqlalchemy import Boolean, Enum, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import BaseModel


class SectionType(enum.StrEnum):
    HALF_TITLE = "half_title"
    TITLE_PAGE = "title_page"
    COPYRIGHT = "copyright"
    DEDICATION = "dedication"
    EPIGRAPH = "epigraph"
    TABLE_OF_CONTENTS = "table_of_contents"
    FOREWORD = "foreword"
    PREFACE = "preface"
    ACKNOWLEDGMENTS_FRONT = "acknowledgments_front"
    INTRODUCTION = "introduction"
    PROLOGUE = "prologue"
    EPILOGUE = "epilogue"
    AFTERWORD = "afterword"
    ACKNOWLEDGMENTS_BACK = "acknowledgments_back"
    APPENDIX = "appendix"
    GLOSSARY = "glossary"
    BIBLIOGRAPHY = "bibliography"
    INDEX = "index"
    ABOUT_AUTHOR = "about_author"
    ALSO_BY = "also_by"
    COLOPHON = "colophon"


class SectionPlacement(enum.StrEnum):
    FRONT_MATTER = "front_matter"
    BACK_MATTER = "back_matter"


class Section(BaseModel):
    __tablename__ = "sections"

    work_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("works.id", ondelete="CASCADE"), nullable=False
    )
    section_type: Mapped[SectionType] = mapped_column(Enum(SectionType), nullable=False)
    placement: Mapped[SectionPlacement] = mapped_column(Enum(SectionPlacement), nullable=False)
    title: Mapped[str | None] = mapped_column(String(500), nullable=True)
    content: Mapped[str] = mapped_column(Text, default="")
    notes: Mapped[str] = mapped_column(Text, default="")
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    include_in_toc: Mapped[bool] = mapped_column(Boolean, default=False)
    include_page_numbers: Mapped[bool] = mapped_column(Boolean, default=False)
    start_recto: Mapped[bool] = mapped_column(Boolean, default=True)

    work = relationship("Work", back_populates="sections")
