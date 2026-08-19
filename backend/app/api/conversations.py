from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.deps import get_current_user
from app.db.engine import get_db
from app.models.conversation import Conversation, ConversationMessage
from app.models.user import User
from app.schemas.conversation import (
    ConversationCreate,
    ConversationListItem,
    ConversationResponse,
    ConversationUpdate,
)

router = APIRouter()


@router.get("/", response_model=list[ConversationListItem])
async def list_conversations(
    work_id: uuid.UUID | None = None,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    stmt = (
        select(
            Conversation,
            func.count(ConversationMessage.id).label("message_count"),
        )
        .outerjoin(ConversationMessage)
        .where(Conversation.user_id == user.id)
        .group_by(Conversation.id)
        .order_by(Conversation.updated_at.desc())
    )
    if work_id:
        stmt = stmt.where(Conversation.work_id == work_id)
    result = await db.execute(stmt)
    rows = result.all()
    return [
        ConversationListItem(
            id=conv.id,
            title=conv.title,
            work_id=conv.work_id,
            persona=conv.persona,
            created_at=conv.created_at,
            updated_at=conv.updated_at,
            message_count=count,
        )
        for conv, count in rows
    ]


@router.post("/", response_model=ConversationResponse, status_code=201)
async def create_conversation(
    data: ConversationCreate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    conv = Conversation(
        user_id=user.id,
        title=data.title,
        work_id=data.work_id,
        persona=data.persona,
    )
    db.add(conv)
    await db.commit()
    await db.refresh(conv, ["messages"])
    return conv


@router.get("/{conversation_id}", response_model=ConversationResponse)
async def get_conversation(
    conversation_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Conversation)
        .where(Conversation.id == conversation_id)
        .options(selectinload(Conversation.messages))
    )
    conv = result.scalar_one_or_none()
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found")
    return conv


@router.patch("/{conversation_id}", response_model=ConversationResponse)
async def update_conversation(
    conversation_id: uuid.UUID,
    data: ConversationUpdate,
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Conversation)
        .where(Conversation.id == conversation_id)
        .options(selectinload(Conversation.messages))
    )
    conv = result.scalar_one_or_none()
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found")
    for key, value in data.model_dump(exclude_unset=True).items():
        setattr(conv, key, value)
    await db.commit()
    await db.refresh(conv, ["messages"])
    return conv


@router.delete("/{conversation_id}", status_code=204)
async def delete_conversation(
    conversation_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Conversation).where(Conversation.id == conversation_id)
    )
    conv = result.scalar_one_or_none()
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found")
    await db.delete(conv)
    await db.commit()
