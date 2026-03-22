"""
대화 기록 CRUD 라우터
"""
import uuid
import logging
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete
from pydantic import BaseModel
from app.core.auth import get_current_user
from app.core.database import get_db
from app.models.conversation import Conversation, Message

logger = logging.getLogger(__name__)
router = APIRouter()


# ── 응답 스키마 ────────────────────────────────────────────────────────────────

class ConversationOut(BaseModel):
    id: uuid.UUID
    title: str
    created_at: str
    updated_at: str

    model_config = {"from_attributes": True}


class MessageOut(BaseModel):
    id: uuid.UUID
    role: str
    content: str
    actions: list | None = None
    tool_results: dict | None = None
    created_at: str

    model_config = {"from_attributes": True}


# ── 엔드포인트 ─────────────────────────────────────────────────────────────────

@router.get("/conversations")
async def list_conversations(
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """현재 사용자의 대화 목록을 최신순으로 반환한다."""
    result = await db.execute(
        select(Conversation)
        .where(Conversation.user_id == user["sub"])
        .order_by(Conversation.updated_at.desc())
    )
    rows = result.scalars().all()
    return [
        {
            "id": str(c.id),
            "title": c.title,
            "created_at": c.created_at.isoformat(),
            "updated_at": c.updated_at.isoformat(),
        }
        for c in rows
    ]


@router.get("/conversations/{conversation_id}/messages")
async def get_messages(
    conversation_id: uuid.UUID,
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """특정 대화의 메시지 목록을 반환한다."""
    conv = await db.get(Conversation, conversation_id)
    if not conv or conv.user_id != user["sub"]:
        raise HTTPException(status_code=404, detail="대화를 찾을 수 없습니다")

    result = await db.execute(
        select(Message)
        .where(Message.conversation_id == conversation_id)
        .order_by(Message.created_at)
    )
    messages = result.scalars().all()
    return [
        {
            "id": str(m.id),
            "role": m.role,
            "content": m.content,
            "actions": m.actions,
            "tool_results": m.tool_results,
            "created_at": m.created_at.isoformat(),
        }
        for m in messages
    ]


@router.delete("/conversations/{conversation_id}", status_code=204)
async def delete_conversation(
    conversation_id: uuid.UUID,
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """대화와 모든 메시지를 삭제한다."""
    conv = await db.get(Conversation, conversation_id)
    if not conv or conv.user_id != user["sub"]:
        raise HTTPException(status_code=404, detail="대화를 찾을 수 없습니다")

    await db.execute(delete(Message).where(Message.conversation_id == conversation_id))
    await db.delete(conv)
    await db.commit()
