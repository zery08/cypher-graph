"""
Coordinator v3 - deepagents(LangGraph) 기반 구현

v2와의 차이:
- raw OpenAI 스트림 루프 대신 deepagents(LangGraph) create_deep_agent 사용
- AgentState / tool 실행 루프를 LangGraph 에 위임
- ToolDef → LangChain StructuredTool 자동 변환
- LangGraph astream(stream_mode="messages") 로 토큰 + reasoning 순서대로 수신
- reasoning 토큰: AIMessageChunk additional_kwargs / content 블록(thinking) 양방향 지원
- native tool calling 미지원 fallback 제거 (deepagents 내부에서 처리)
"""
import json
import logging
import uuid
from datetime import datetime
from typing import AsyncGenerator, Optional, Any
from typing import get_type_hints

from langchain_core.messages import (
    AIMessageChunk,
    ToolMessage,
    HumanMessage,
    SystemMessage,
    AIMessage,
)
from langchain_core.tools import StructuredTool
from langchain_openai import ChatOpenAI
from pydantic import BaseModel, create_model
from deepagents import create_deep_agent

from app.core.config import settings
from app.llm.prompts import COORDINATOR_SYSTEM_PROMPT
from app.llm.tools import load_all_tools, ToolDef
from app.llm.coordinator_v2 import (
    _schema_snippet,
    _parse_tool_result,
    _merge_tool_result,
    _merge_actions,
    HISTORY_LIMIT,
    AgentState,
    _split_think_content as _split_think_tags,
)
from app.schemas.chat import ChatResponse, ChatAction, ToolResult, StepInfo

logger = logging.getLogger(__name__)

# ── 상수 ────────────────────────────────────────────────────────────────────────

# OpenAI spec type → Python type 매핑
_TYPE_MAP: dict[str, type] = {
    "string": str,
    "number": float,
    "integer": int,
    "boolean": bool,
    "array": list,
    "object": dict,
}


# ── ToolDef → LangChain StructuredTool 변환 ────────────────────────────────────

def _build_args_model(tool_def: ToolDef) -> type[BaseModel]:
    """
    TOOL_SPEC 의 parameters 스키마를 Pydantic 모델로 변환한다.
    LangChain StructuredTool 의 args_schema 에 사용된다.
    """
    spec_params = tool_def.spec["function"].get("parameters", {})
    properties: dict[str, Any] = spec_params.get("properties", {})
    required: list[str] = spec_params.get("required", [])

    fields: dict[str, Any] = {}
    for name, prop in properties.items():
        py_type = _TYPE_MAP.get(prop.get("type", "string"), str)
        description = prop.get("description", "")
        if name in required:
            # 필수 필드: (타입, FieldInfo)
            from pydantic import Field
            fields[name] = (py_type, Field(..., description=description))
        else:
            fields[name] = (Optional[py_type], None)  # type: ignore[assignment]

    return create_model(f"{tool_def.name}_Args", **fields)


def _tool_def_to_langchain(tool_def: ToolDef) -> StructuredTool:
    """ToolDef 를 LangChain StructuredTool 로 변환한다."""
    args_model = _build_args_model(tool_def)

    def _run(**kwargs: Any) -> str:
        return tool_def.run(kwargs)

    return StructuredTool.from_function(
        func=_run,
        name=tool_def.name,
        description=tool_def.spec["function"]["description"],
        args_schema=args_model,
    )


# ── LLM 생성 ───────────────────────────────────────────────────────────────────

def _make_coordinator_llm() -> ChatOpenAI:
    """coordinator용 ChatOpenAI 인스턴스 (OpenRouter 호환)."""
    return ChatOpenAI(
        model=settings.coordinator_model,
        api_key=settings.coordinator_api_key,
        base_url=settings.coordinator_base_url,
        max_tokens=settings.coordinator_max_tokens,
        temperature=0.1,
    )


# ── 시스템 프롬프트 ─────────────────────────────────────────────────────────────

def _build_system_prompt() -> str:
    return COORDINATOR_SYSTEM_PROMPT.format(
        current_date=datetime.now().strftime("%Y-%m-%d"),
        schema=_schema_snippet(),
    )


# ── 입력 메시지 구성 ────────────────────────────────────────────────────────────

def _build_input_messages(
    history: list[dict],
    context: dict,
    message: str,
) -> list[dict]:
    msgs: list[dict] = []
    for m in history[-HISTORY_LIMIT:]:
        msgs.append({"role": m["role"], "content": m["content"]})
    prefix_parts: list[str] = []
    if context.get("current_query"):
        prefix_parts.append(f"[현재 실행 쿼리: {context['current_query']}]")
    if context.get("selected_node"):
        prefix_parts.append(f"[선택된 노드: {context['selected_node']}]")
    content = "\n".join(prefix_parts + [message]) if prefix_parts else message
    msgs.append({"role": "user", "content": content})
    return msgs


# ── reasoning 추출 ─────────────────────────────────────────────────────────────

def _extract_reasoning_from_chunk(chunk: AIMessageChunk) -> str:
    """
    AIMessageChunk 에서 reasoning/thinking 텍스트를 추출한다.
    지원 형태:
    1. additional_kwargs["reasoning"] / ["reasoning_content"] / ["thinking"]  — OpenRouter delta
    2. content = [{"type": "thinking", "thinking": "..."}]  — Claude extended thinking
    3. <think>...</think> 태그 — QwQ / DeepSeek-R1
    """
    ak = chunk.additional_kwargs or {}
    rc = ak.get("reasoning") or ak.get("reasoning_content") or ak.get("thinking") or ""
    if rc:
        return rc

    content = chunk.content
    if isinstance(content, list):
        parts = [
            b.get("thinking", "")
            for b in content
            if isinstance(b, dict) and b.get("type") == "thinking"
        ]
        return "\n".join(parts)

    return ""


def _extract_text_from_content(content: str | list) -> str:
    """AIMessageChunk.content 에서 텍스트만 추출한다."""
    if isinstance(content, str):
        return content
    # 멀티모달 블록 리스트
    parts = [
        b.get("text", "")
        for b in content
        if isinstance(b, dict) and b.get("type") == "text"
    ]
    return "".join(parts)


# ── 스트리밍 이벤트 처리 ────────────────────────────────────────────────────────

async def _stream_deepagent(
    agent,
    input_messages: list[dict],
    tools_by_name: dict[str, ToolDef],
    config: dict,
) -> AsyncGenerator[str, None]:
    """
    deepagents 스트림을 소비하여 우리 형식(SSE JSON 문자열)으로 변환한다.

    LangGraph stream_mode="messages" 이벤트:
      - (AIMessageChunk, metadata) : 토큰 스트림
      - (ToolMessage, metadata)    : tool 실행 결과

    추론 순서 보장:
      reasoning_token → token → step_start → step_end → done
    """
    state = AgentState()

    # tool call 누적 버퍼 (여러 chunk 에 걸쳐 완성됨)
    pending_tool_calls: dict[str, dict] = {}  # call_id → {name, args_parts}
    emitted_step_starts: set[str] = set()

    async for chunk, metadata in agent.astream(
        {"messages": input_messages},
        config=config,
        stream_mode="messages",
    ):
        node = metadata.get("langgraph_node", "")

        # ── AI 응답 청크 ─────────────────────────────────────────────────────
        if isinstance(chunk, AIMessageChunk):
            # 1) reasoning 토큰
            reasoning = _extract_reasoning_from_chunk(chunk)
            if reasoning:
                state.add_reasoning(reasoning)
                yield json.dumps(
                    {"type": "reasoning_token", "content": reasoning},
                    ensure_ascii=False,
                )

            # 2) 텍스트 토큰 (<think> 태그 포함 가능)
            raw_text = _extract_text_from_content(chunk.content)
            if raw_text:
                tag_reasoning, clean_text = _split_think_tags(raw_text)
                if tag_reasoning:
                    state.add_reasoning(tag_reasoning)
                    yield json.dumps(
                        {"type": "reasoning_token", "content": tag_reasoning},
                        ensure_ascii=False,
                    )
                if clean_text:
                    # tool_call 대기 중이 아닐 때만 토큰 전송
                    if not pending_tool_calls:
                        yield json.dumps(
                            {"type": "token", "content": clean_text},
                            ensure_ascii=False,
                        )

            # 3) tool call 청크 누적
            if chunk.tool_call_chunks:
                for tc_chunk in chunk.tool_call_chunks:
                    call_id = tc_chunk.get("id") or tc_chunk.get("index", "")
                    call_id = str(call_id)
                    if call_id not in pending_tool_calls:
                        pending_tool_calls[call_id] = {"name": "", "args_parts": []}
                    if tc_chunk.get("name"):
                        pending_tool_calls[call_id]["name"] += tc_chunk["name"]
                    if tc_chunk.get("args"):
                        pending_tool_calls[call_id]["args_parts"].append(tc_chunk["args"])

                # 이름이 완성된 tool call 에 step_start 전송
                for call_id, tc in pending_tool_calls.items():
                    if tc["name"] and call_id not in emitted_step_starts:
                        tool_def = tools_by_name.get(tc["name"])
                        emitted_step_starts.add(call_id)
                        yield json.dumps({
                            "type": "step_start",
                            "tool": tool_def.label if tool_def else tc["name"],
                            "tool_key": tc["name"],
                            "input": "".join(tc["args_parts"])[:2000],
                            "reasoning": state.reasoning.strip() or None,
                        }, ensure_ascii=False)

        # ── Tool 실행 결과 ────────────────────────────────────────────────────
        elif isinstance(chunk, ToolMessage):
            fn_name = chunk.name or ""
            output = chunk.content if isinstance(chunk.content, str) else json.dumps(chunk.content)
            tool_def = tools_by_name.get(fn_name)

            tool_result, actions, summary = _parse_tool_result(fn_name, output)
            state.merge_tool(tool_result, actions)

            # 해당 call_id 로 입력 args 복원
            call_id = chunk.tool_call_id or ""
            args_str = ""
            if call_id in pending_tool_calls:
                args_str = "".join(pending_tool_calls[call_id]["args_parts"])
                del pending_tool_calls[call_id]

            state.steps.append(StepInfo(
                tool=tool_def.label if tool_def else fn_name,
                tool_key=fn_name,
                input=args_str[:2000],
                output=summary,
                reasoning=None,
            ))

            yield json.dumps(
                {"type": "step_end", "tool_key": fn_name, "output": summary},
                ensure_ascii=False,
            )

    # 스트림 완료 → done 이벤트
    yield json.dumps(state.done_payload(), ensure_ascii=False)


# ── 공개 API ──────────────────────────────────────────────────────────────────

async def stream_coordinator(
    message: str,
    history: list[dict] = [],
    context: dict = {},
) -> AsyncGenerator[str, None]:
    """
    coordinator v3 스트리밍 실행.
    deepagents(LangGraph) 기반으로 tool 루프를 처리한다.
    """
    tool_defs = load_all_tools()
    tools_by_name = {t.name: t for t in tool_defs}
    lc_tools = [_tool_def_to_langchain(t) for t in tool_defs]

    llm = _make_coordinator_llm()
    agent = create_deep_agent(
        model=llm,
        tools=lc_tools,
        system_prompt=_build_system_prompt(),
        checkpointer=False,  # 상태 없이 stateless 실행 (히스토리는 직접 관리)
    )

    input_messages = _build_input_messages(history, context, message)
    config = {"configurable": {"thread_id": str(uuid.uuid4())}}

    try:
        async for event in _stream_deepagent(agent, input_messages, tools_by_name, config):
            yield event
    except Exception as e:
        logger.error(f"stream_coordinator(v3) 오류: {e}", exc_info=True)
        yield json.dumps({"type": "error", "content": str(e)}, ensure_ascii=False)


async def run_coordinator(
    message: str,
    history: list[dict] = [],
    context: dict = {},
) -> ChatResponse:
    """비스트리밍 실행 (stream_coordinator 를 내부에서 소비)."""
    tokens: list[str] = []
    steps: list[StepInfo] = []
    all_actions: list[ChatAction] = []
    final_tool_result = ToolResult()
    reasoning_parts: list[str] = []

    try:
        async for raw in stream_coordinator(message, history, context):
            event = json.loads(raw)
            t = event.get("type")
            if t == "token":
                tokens.append(event.get("content", ""))
            elif t == "reasoning_token":
                reasoning_parts.append(event.get("content", ""))
            elif t == "done":
                all_actions = [ChatAction(**a) for a in event.get("actions", [])]
                tr = event.get("tool_results", {})
                final_tool_result = ToolResult(**tr) if tr else ToolResult()
                steps = [StepInfo(**s) for s in event.get("steps", [])]
                break
            elif t == "error":
                return ChatResponse(message=f"오류: {event.get('content', '')}")
    except Exception as e:
        logger.error(f"run_coordinator(v3) 실패: {e}", exc_info=True)
        return ChatResponse(message=f"처리 중 오류가 발생했습니다: {str(e)}")

    return ChatResponse(
        message="".join(tokens) or "처리가 완료되었습니다.",
        actions=all_actions,
        tool_results=final_tool_result,
        steps=steps,
        reasoning="".join(reasoning_parts).strip() or None,
    )
