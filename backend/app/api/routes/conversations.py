"""
대화 기록 CRUD 라우터
"""
import uuid
import logging
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
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
    steps: list | None = None
    reasoning: str | None = None
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
        .where(
            Conversation.user_id == user["id"],
            Conversation.deleted_at.is_(None),
        )
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
    if not conv or conv.user_id != user["id"]:
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
            "steps": m.steps,
            "reasoning": m.reasoning,
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
    if not conv or conv.user_id != user["id"] or conv.deleted_at is not None:
        raise HTTPException(status_code=404, detail="대화를 찾을 수 없습니다")

    conv.deleted_at = datetime.now(timezone.utc)
    await db.commit()


# ── Admin 전용 엔드포인트 ──────────────────────────────────────────────────────

ADMIN_USER_IDS = {"admin"}  # 추후 환경변수로 확장 가능


def _require_admin(user: dict) -> dict:
    if user["id"] not in ADMIN_USER_IDS:
        raise HTTPException(status_code=403, detail="관리자 권한이 필요합니다")
    return user


@router.get("/admin/conversations")
async def admin_list_all_conversations(
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """[Admin] 삭제된 대화를 포함한 전체 대화 목록을 반환한다."""
    _require_admin(user)
    result = await db.execute(
        select(Conversation).order_by(Conversation.updated_at.desc())
    )
    rows = result.scalars().all()
    return [
        {
            "id": str(c.id),
            "user_id": c.user_id,
            "title": c.title,
            "created_at": c.created_at.isoformat(),
            "updated_at": c.updated_at.isoformat(),
            "deleted_at": c.deleted_at.isoformat() if c.deleted_at else None,
        }
        for c in rows
    ]
