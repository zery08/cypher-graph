"""
채팅 엔드포인트 - coordinator LLM 실행 + 대화 기록 저장
"""
import uuid
import json
import logging
from fastapi import APIRouter, HTTPException, Depends
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from pydantic import BaseModel
from app.schemas.chat import ChatRequest, ChatResponse
from app.llm.coordinator_v3 import run_coordinator, stream_coordinator
from app.core.auth import get_current_user_optional
from app.core.database import get_db
from app.models.conversation import Conversation, Message

logger = logging.getLogger(__name__)
router = APIRouter()


class ChatRequestWithConversation(ChatRequest):
    conversation_id: str | None = None  # 기존 대화에 이어붙이려면 전달


@router.post("/chat", response_model=ChatResponse)
async def chat(
    request: ChatRequestWithConversation,
    user: dict | None = Depends(get_current_user_optional),
    db: AsyncSession = Depends(get_db),
):
    """
    사용자 메시지를 coordinator에 전달하고
    tool 호출 결과와 최종 답변을 반환한다.
    로그인 상태이면 대화 기록을 PostgreSQL에 저장한다.
    """
    try:
        history = [msg.model_dump() for msg in request.history]
        response = await run_coordinator(
            message=request.message,
            history=history,
            context=request.context,
        )
    except Exception as e:
        logger.error(f"채팅 처리 실패: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"채팅 처리 실패: {str(e)}")

    # 로그인 상태이고 DB가 사용 가능할 때만 대화 기록 저장
    if user and db is not None:
        try:
            await _save_messages(db, user["id"], request, response)
        except Exception as e:
            logger.warning(f"대화 기록 저장 실패 (무시): {e}")

    return response


@router.post("/chat/stream")
async def chat_stream(
    request: ChatRequestWithConversation,
    user: dict | None = Depends(get_current_user_optional),
    db: AsyncSession = Depends(get_db),
):
    """
    coordinator를 SSE 스트리밍으로 실행한다.
    이벤트 타입: step_start | step_end | token | done | error
    """
    history = [msg.model_dump() for msg in request.history]

    async def generate():
        final_data = None
        tokens = []
        try:
            async for event_json in stream_coordinator(
                message=request.message,
                history=history,
                context=request.context,
            ):
                yield f"data: {event_json}\n\n"
                try:
                    event = json.loads(event_json)
                    if event.get("type") == "token":
                        tokens.append(event.get("content", ""))
                    elif event.get("type") == "done":
                        final_data = event
                except Exception:
                    pass
        except Exception as e:
            yield f"data: {json.dumps({'type': 'error', 'content': str(e)})}\n\n"
        finally:
            yield "data: [DONE]\n\n"

        # 스트리밍 완료 후 대화 기록 저장 (Depends 세션이 닫혀있으므로 새 세션 사용)
        if final_data and user:
            try:
                from app.schemas.chat import ChatResponse, ToolResult, ChatAction, StepInfo
                from app.core.database import AsyncSessionLocal
                response = ChatResponse(
                    message="".join(tokens),
                    actions=[ChatAction(**a) for a in (final_data.get("actions") or [])],
                    tool_results=ToolResult(**(final_data.get("tool_results") or {})),
                    steps=[StepInfo(**s) for s in (final_data.get("steps") or [])],
                    reasoning=final_data.get("reasoning"),
                )
                async with AsyncSessionLocal() as fresh_db:
                    await _save_messages(fresh_db, user["id"], request, response)
            except Exception as e:
                logger.warning(f"스트리밍 대화 기록 저장 실패: {e}")

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


async def _save_messages(
    db: AsyncSession,
    user_id: str,
    request: ChatRequestWithConversation,
    response: ChatResponse,
) -> None:
    """대화 메시지를 DB에 저장한다. 대화가 없으면 새로 생성한다."""
    conv_id = None
    if request.conversation_id:
        try:
            conv_id = uuid.UUID(request.conversation_id)
        except ValueError:
            pass

    # 기존 대화 확인 또는 신규 생성
    conv = None
    if conv_id:
        result = await db.execute(
            select(Conversation).where(
                Conversation.id == conv_id,
                Conversation.user_id == user_id,
            )
        )
        conv = result.scalar_one_or_none()

    if conv is None:
        # 첫 메시지 앞 30자를 제목으로 사용
        title = request.message[:30] + ("..." if len(request.message) > 30 else "")
        conv = Conversation(user_id=user_id, title=title)
        db.add(conv)
        await db.flush()  # id 확보

    # 사용자 메시지 저장
    db.add(Message(
        conversation_id=conv.id,
        role="user",
        content=request.message,
    ))

    # 어시스턴트 응답 저장
    db.add(Message(
        conversation_id=conv.id,
        role="assistant",
        content=response.message,
        actions=[a.model_dump() for a in response.actions] if response.actions else None,
        tool_results=response.tool_results.model_dump() if response.tool_results else None,
        steps=[s.model_dump() for s in response.steps] if response.steps else None,
        reasoning=response.reasoning or None,
    ))

    await db.commit()
