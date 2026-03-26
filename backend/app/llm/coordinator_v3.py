"""
Coordinator v3 - deepagents(LangGraph) 기반 구현

deepagents가 agent loop(tool 선택·실행·반복)를 담당한다.
이 파일의 역할:
  1. ToolDef → LangChain StructuredTool 변환
  2. LangGraph astream 이벤트 → SSE JSON 변환
  3. reasoning 토큰 순서대로 전달
"""
import json
import logging
import uuid
from datetime import datetime
from typing import AsyncGenerator, Optional, Any

from langchain_core.messages import AIMessageChunk, ToolMessage
from langchain_core.tools import StructuredTool
from langchain_openai import ChatOpenAI
from pydantic import BaseModel, Field, create_model
from deepagents import create_deep_agent

from app.core.config import settings
from app.llm.prompts import COORDINATOR_SYSTEM_PROMPT
from app.llm.tools import load_all_tools, ToolDef
from app.llm.coordinator_v2 import (
    _schema_snippet,
    _parse_tool_result,
    _split_think_content,
    HISTORY_LIMIT,
)
from app.schemas.chat import ChatResponse, ChatAction, ToolResult, StepInfo

logger = logging.getLogger(__name__)

_TYPE_MAP: dict[str, type] = {
    "string": str, "number": float, "integer": int,
    "boolean": bool, "array": list, "object": dict,
}


# ── ToolDef → LangChain StructuredTool ────────────────────────────────────────

def _to_langchain_tool(tool_def: ToolDef) -> StructuredTool:
    """ToolDef 를 LangChain StructuredTool 로 변환한다."""
    spec_params = tool_def.spec["function"].get("parameters", {})
    properties = spec_params.get("properties", {})
    required = spec_params.get("required", [])

    fields: dict[str, Any] = {}
    for name, prop in properties.items():
        py_type = _TYPE_MAP.get(prop.get("type", "string"), str)
        desc = prop.get("description", "")
        fields[name] = (py_type, Field(..., description=desc)) if name in required else (Optional[py_type], None)

    args_model = create_model(f"{tool_def.name}_Args", **fields)

    def _run(**kwargs: Any) -> str:
        return tool_def.run(kwargs)

    return StructuredTool.from_function(
        func=_run,
        name=tool_def.name,
        description=tool_def.spec["function"]["description"],
        args_schema=args_model,
    )


# ── 공개 API ──────────────────────────────────────────────────────────────────

async def stream_coordinator(
    message: str,
    history: list[dict] = [],
    context: dict = {},
) -> AsyncGenerator[str, None]:
    """
    coordinator v3 스트리밍 실행.
    deepagents(LangGraph) 기반으로 tool 루프를 처리한다.
    reasoning_token → token → step_start → step_end → done 순서 보장.
    """
    tool_defs = load_all_tools()
    tools_by_name = {t.name: t for t in tool_defs}

    llm = ChatOpenAI(
        model=settings.coordinator_model,
        api_key=settings.coordinator_api_key,
        base_url=settings.coordinator_base_url,
        max_tokens=settings.coordinator_max_tokens,
        temperature=0.1,
    )

    agent = create_deep_agent(
        model=llm,
        tools=[_to_langchain_tool(t) for t in tool_defs],
        system_prompt=COORDINATOR_SYSTEM_PROMPT.format(
            current_date=datetime.now().strftime("%Y-%m-%d"),
            schema=_schema_snippet(),
        ),
        checkpointer=False,
    )

    # 입력 메시지 구성
    msgs: list[dict] = [{"role": m["role"], "content": m["content"]} for m in history[-HISTORY_LIMIT:]]
    prefix = "\n".join(
        p for p in [
            f"[현재 실행 쿼리: {context['current_query']}]" if context.get("current_query") else "",
            f"[선택된 노드: {context['selected_node']}]" if context.get("selected_node") else "",
        ] if p
    )
    msgs.append({"role": "user", "content": f"{prefix}\n{message}" if prefix else message})

    # 누적 상태
    accumulated_reasoning = ""
    accumulated_actions: list[ChatAction] = []
    accumulated_tool_result = ToolResult()
    steps: list[StepInfo] = []
    # index(int) → {id, name, args_parts}
    # tool_call_chunk 첫 번째에만 id가 오고 이후엔 None이므로 index를 primary key로 사용
    pending_calls: dict[int, dict] = {}
    emitted_starts: set[int] = set()

    try:
        async for chunk, metadata in agent.astream(
            {"messages": msgs},
            config={"configurable": {"thread_id": str(uuid.uuid4())}},
            stream_mode="messages",
        ):
            node = metadata.get("langgraph_node", "")

            if isinstance(chunk, AIMessageChunk):
                # 1) reasoning (additional_kwargs 방식 - OpenRouter 등)
                ak = chunk.additional_kwargs or {}
                rc = ak.get("reasoning") or ak.get("reasoning_content") or ak.get("thinking") or ""
                if rc:
                    accumulated_reasoning += rc
                    yield json.dumps({"type": "reasoning_token", "content": rc}, ensure_ascii=False)

                # 2) 텍스트 토큰 — model 노드의 최종 응답만 yield
                #    tools 노드의 AIMessageChunk는 GraphCypherQAChain 내부 출력이므로 무시
                if node == "model":
                    raw = chunk.content if isinstance(chunk.content, str) else "".join(
                        b.get("text", "") for b in chunk.content
                        if isinstance(b, dict) and b.get("type") == "text"
                    )
                    # Claude thinking 블록
                    if isinstance(chunk.content, list):
                        thinking = "\n".join(
                            b.get("thinking", "") for b in chunk.content
                            if isinstance(b, dict) and b.get("type") == "thinking"
                        )
                        if thinking:
                            accumulated_reasoning += thinking
                            yield json.dumps({"type": "reasoning_token", "content": thinking}, ensure_ascii=False)

                    if raw:
                        tag_reasoning, clean = _split_think_content(raw)
                        if tag_reasoning:
                            accumulated_reasoning += tag_reasoning
                            yield json.dumps({"type": "reasoning_token", "content": tag_reasoning}, ensure_ascii=False)
                        # tool call 대기 중이 아닐 때만 토큰 전송
                        if clean and not pending_calls:
                            yield json.dumps({"type": "token", "content": clean}, ensure_ascii=False)

                # 3) tool call 청크 누적
                #    첫 chunk: index=N, id="call_xxx", name="tool_name", args=""
                #    이후 chunk: index=N, id=None, name=None, args="{...}"
                #    → index를 key로 사용해 하나의 entry에 합산
                for tc in chunk.tool_call_chunks or []:
                    idx = tc.get("index") or 0
                    if idx not in pending_calls:
                        pending_calls[idx] = {"id": None, "name": "", "args_parts": []}
                    if tc.get("id"):
                        pending_calls[idx]["id"] = tc["id"]
                    if tc.get("name"):
                        pending_calls[idx]["name"] += tc["name"]
                    if tc.get("args"):
                        pending_calls[idx]["args_parts"].append(tc["args"])

                # 이름이 완성된 entry에 step_start 전송
                for idx, tc in pending_calls.items():
                    if tc["name"] and idx not in emitted_starts:
                        td = tools_by_name.get(tc["name"])
                        emitted_starts.add(idx)
                        yield json.dumps({
                            "type": "step_start",
                            "tool": td.label if td else tc["name"],
                            "tool_key": tc["name"],
                            "input": "".join(tc["args_parts"])[:2000],
                            "reasoning": accumulated_reasoning.strip() or None,
                        }, ensure_ascii=False)

            elif isinstance(chunk, ToolMessage):
                fn_name = chunk.name or ""
                output = chunk.content if isinstance(chunk.content, str) else json.dumps(chunk.content)
                td = tools_by_name.get(fn_name)

                tool_result, actions, summary = _parse_tool_result(fn_name, output)

                # tool_result 누적
                if tool_result:
                    for f in ("graph", "table", "chart", "cypher"):
                        val = getattr(tool_result, f, None)
                        if val is not None:
                            setattr(accumulated_tool_result, f, val)
                    if tool_result.summary:
                        accumulated_tool_result.summary = (
                            f"{accumulated_tool_result.summary}\n{tool_result.summary}".strip()
                            if accumulated_tool_result.summary else tool_result.summary
                        )
                seen = {json.dumps(a.model_dump(), sort_keys=True) for a in accumulated_actions}
                for a in actions:
                    key = json.dumps(a.model_dump(), sort_keys=True)
                    if key not in seen:
                        accumulated_actions.append(a)
                        seen.add(key)

                # tool_call_id로 pending_calls에서 해당 entry 찾아 제거
                call_id = chunk.tool_call_id or ""
                key_to_remove = next((k for k, v in pending_calls.items() if v.get("id") == call_id), None)
                args_str = ""
                if key_to_remove is not None:
                    args_str = "".join(pending_calls.pop(key_to_remove)["args_parts"])

                steps.append(StepInfo(
                    tool=td.label if td else fn_name,
                    tool_key=fn_name,
                    input=args_str[:2000],
                    output=summary,
                    reasoning=None,
                ))
                yield json.dumps({"type": "step_end", "tool_key": fn_name, "output": summary}, ensure_ascii=False)

        yield json.dumps({
            "type": "done",
            "actions": [a.model_dump() for a in accumulated_actions],
            "tool_results": accumulated_tool_result.model_dump(),
            "steps": [s.model_dump() for s in steps],
            "reasoning": accumulated_reasoning.strip() or None,
        }, ensure_ascii=False)

    except Exception as e:
        logger.error(f"stream_coordinator(v3) 오류: {e}", exc_info=True)
        yield json.dumps({"type": "error", "content": str(e)}, ensure_ascii=False)


async def run_coordinator(
    message: str,
    history: list[dict] = [],
    context: dict = {},
) -> ChatResponse:
    """비스트리밍 실행."""
    tokens: list[str] = []
    reasoning_parts: list[str] = []
    all_actions: list[ChatAction] = []
    tool_result = ToolResult()
    steps: list[StepInfo] = []

    try:
        async for raw in stream_coordinator(message, history, context):
            event = json.loads(raw)
            t = event.get("type")
            if t == "token":
                tokens.append(event["content"])
            elif t == "reasoning_token":
                reasoning_parts.append(event["content"])
            elif t == "done":
                all_actions = [ChatAction(**a) for a in event.get("actions", [])]
                tr = event.get("tool_results", {})
                tool_result = ToolResult(**tr) if tr else ToolResult()
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
        tool_results=tool_result,
        steps=steps,
        reasoning="".join(reasoning_parts).strip() or None,
    )
