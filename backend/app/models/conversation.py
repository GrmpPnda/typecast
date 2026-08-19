from __future__ import annotations

import uuid

from sqlalchemy import ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import BaseModel


class Conversation(BaseModel):
    __tablename__ = "conversations"

    user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=True
    )
    title: Mapped[str] = mapped_column(String(500), default="New conversation")
    work_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("works.id", ondelete="SET NULL"), nullable=True
    )
    persona: Mapped[str] = mapped_column(String(50), default="author")

    messages = relationship(
        "ConversationMessage",
        back_populates="conversation",
        lazy="selectin",
        cascade="all, delete-orphan",
        order_by="ConversationMessage.sort_order",
    )


class ConversationMessage(BaseModel):
    __tablename__ = "conversation_messages"

    conversation_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("conversations.id", ondelete="CASCADE"), nullable=False
    )
    role: Mapped[str] = mapped_column(String(20), nullable=False)
    content: Mapped[str] = mapped_column(Text, default="")
    tool_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)

    conversation = relationship("Conversation", back_populates="messages")
