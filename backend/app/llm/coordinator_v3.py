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
import re
import time
import uuid
from datetime import datetime
from pathlib import Path
from typing import AsyncGenerator, Optional, Any

from langchain_core.messages import AIMessageChunk, ToolMessage
from langchain_core.outputs import ChatGenerationChunk
from langchain_core.tools import StructuredTool
from langchain_openai import ChatOpenAI
from pydantic import BaseModel, Field, create_model
from deepagents import create_deep_agent


class ReasoningChatOpenAI(ChatOpenAI):
    """
    GLM-4.7 등 model_extra['reasoning'] 필드를 반환하는 모델용 ChatOpenAI 래퍼.
    LangChain이 기본적으로 무시하는 delta['reasoning']을
    AIMessageChunk.additional_kwargs['reasoning']으로 전달한다.
    """

    def _convert_chunk_to_generation_chunk(
        self,
        chunk: dict,
        default_chunk_class: type,
        base_generation_info: dict | None,
    ) -> ChatGenerationChunk | None:
        gen = super()._convert_chunk_to_generation_chunk(
            chunk, default_chunk_class, base_generation_info
        )
        if gen is None:
            return None

        # delta에서 reasoning 추출 후 additional_kwargs에 주입
        choices = chunk.get("choices") or chunk.get("chunk", {}).get("choices") or []
        if choices:
            delta = choices[0].get("delta") or {}
            reasoning = delta.get("reasoning") or ""
            if reasoning and isinstance(gen.message, AIMessageChunk):
                gen.message.additional_kwargs["reasoning"] = reasoning

        return gen

from app.core.config import settings
from app.llm.prompts import COORDINATOR_SYSTEM_PROMPT
from app.llm.tools import load_all_tools, ToolDef
from app.schemas.chat import ChatResponse, ChatAction, ToolResult, StepInfo

HISTORY_LIMIT = 6

# ── 스키마 스니펫 ──────────────────────────────────────────────────────────────

def _schema_snippet() -> str:
    try:
        from app.services.neo4j_service import get_schema_info
        schema = get_schema_info()
        lines = ["## Neo4j 스키마"]
        for label in schema.get("node_labels", []):
            props = schema.get("properties", {}).get(label, [])
            lines.append(f"- 노드 {label}: {', '.join(props)}")
        for rel in schema.get("relationship_types", []):
            lines.append(f"- 관계 {rel}")
        return "\n".join(lines)
    except Exception as e:
        logger.warning(f"스키마 주입 실패: {e}")
        return ""


# ── 로깅 헬퍼 ─────────────────────────────────────────────────────────────────

def _fmt_messages(msgs: list[dict]) -> str:
    lines = []
    for m in msgs:
        role = m.get("role", "").upper()
        content = str(m.get("content") or "")[:500]
        lines.append(f"  [{role}] {content}")
    return "\n".join(lines)


# ── reasoning <think> 태그 분리 ───────────────────────────────────────────────

_THINK_TAG_RE = re.compile(r"<think>(.*?)</think>", re.DOTALL)


def _split_think_content(text: str) -> tuple[str, str]:
    reasoning_parts = _THINK_TAG_RE.findall(text)
    clean = _THINK_TAG_RE.sub("", text)
    return "\n".join(reasoning_parts).strip(), clean


# ── tool 결과 파싱 ─────────────────────────────────────────────────────────────

def _parse_tool_result(tool_name: str, output: str) -> tuple[ToolResult | None, list[ChatAction], str]:
    actions: list[ChatAction] = []
    summary = output[:2000]
    try:
        data = json.loads(output)
        if "error" in data:
            return None, [], f"오류: {data['error']}"

        if tool_name == "graph_cypher_qa_tool":
            result = ToolResult(
                cypher=data.get("cypher", ""),
                graph={
                    "nodes": data.get("nodes", []),
                    "edges": data.get("edges", []),
                    "raw": data.get("result", data.get("raw", [])),
                },
                table=data.get("result", data.get("raw", [])),
                summary=data.get("answer", ""),
            )
            row_count = data.get("row_count", "?")
            cypher = data.get("cypher", "")
            summary = f"{row_count}건 반환"
            if data.get("empty_result"):
                summary = "조회 결과 0건"
            if cypher:
                summary += f"\n```cypher\n{cypher}\n```"
                actions.append(ChatAction(type="apply_query", query=cypher))
            if data.get("followup_hint"):
                summary += f"\n후속 제안: {data['followup_hint']}"
            tab = "graph" if data.get("nodes") else "table"
            actions.append(ChatAction(type="open_tab", tab=tab))
            return result, actions, summary

        if tool_name == "chart_build_tool":
            chart_type = data.get("chartType", "line")
            x_key = data.get("xKey", "")
            y_keys = data.get("yKeys") or []
            title = data.get("title", "")
            stats = data.get("stats", {})
            row_count = data.get("row_count", "?")
            chart_config: dict = {
                "chartType": chart_type,
                "xKey": x_key,
                "yKeys": y_keys,
                "title": title,
                "stats": stats,
            }
            summary = f"차트 생성: {chart_type}"
            if title:
                summary += f" — {title}"
            if row_count != "?":
                summary += f" ({row_count}건)"
            actions.append(ChatAction(type="open_tab", tab="chart"))
            return ToolResult(chart=chart_config, summary=summary), actions, summary

    except Exception:
        pass
    return None, [], summary

logger = logging.getLogger(__name__)

_TYPE_MAP: dict[str, type] = {
    "string": str, "number": float, "integer": int,
    "boolean": bool, "array": list, "object": dict,
}
_DEEPAGENT_DIR = Path(__file__).with_name("deepagents")


def _preview_text(value: Any, limit: int = 300) -> str:
    if value is None:
        return ""
    if not isinstance(value, str):
        try:
            value = json.dumps(value, ensure_ascii=False)
        except Exception:
            value = repr(value)
    value = value.replace("\n", "\\n")
    return value if len(value) <= limit else f"{value[:limit]}..."


def _existing_deepagent_paths(*paths: Path) -> list[str]:
    resolved: list[str] = []
    for path in paths:
        if path.exists():
            resolved.append(str(path))
        else:
            logger.warning(f"deepagents asset 누락: {path}")
    return resolved


def _build_deep_agent(tool_defs: list[ToolDef]):
    """현재 프로젝트용 deep agent를 구성한다."""
    langchain_tools = [_to_langchain_tool(t) for t in tool_defs]
    memory_paths = _existing_deepagent_paths(_DEEPAGENT_DIR / "AGENTS.md") or None
    skill_paths = _existing_deepagent_paths(_DEEPAGENT_DIR / "skills") or None

    logger.info(
        f"[coordinator_v3] deepagent 구성 tools={[t.name for t in tool_defs]} "
        f"memory={memory_paths or []} skills={skill_paths or []}"
    )

    return create_deep_agent(
        model=ReasoningChatOpenAI(
            model=settings.coordinator_model,
            api_key=settings.coordinator_api_key,
            base_url=settings.coordinator_base_url,
            max_tokens=settings.coordinator_max_tokens,
            temperature=0.1,
        ),
        tools=langchain_tools,
        system_prompt=COORDINATOR_SYSTEM_PROMPT.format(
            current_date=datetime.now().strftime("%Y-%m-%d"),
            schema=_schema_snippet(),
        ),
        memory=memory_paths,
        skills=skill_paths,
        checkpointer=False,
        name="semiconductor-data-agent",
    )


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
        started_at = time.monotonic()
        logger.info(
            f"[tool_wrapper] 시작 tool={tool_def.name} label={tool_def.label} "
            f"args={_preview_text(kwargs, 800)}"
        )
        try:
            result = tool_def.run(kwargs)
            elapsed_ms = (time.monotonic() - started_at) * 1000
            logger.info(
                f"[tool_wrapper] 완료 tool={tool_def.name} elapsed_ms={elapsed_ms:.1f} "
                f"output_len={len(result)} output={_preview_text(result, 800)}"
            )
            return result
        except Exception as e:
            elapsed_ms = (time.monotonic() - started_at) * 1000
            logger.error(
                f"[tool_wrapper] 실패 tool={tool_def.name} elapsed_ms={elapsed_ms:.1f} "
                f"args={_preview_text(kwargs, 800)} error={e}",
                exc_info=True,
            )
            raise

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
    request_id = uuid.uuid4().hex[:8]
    thread_id = str(uuid.uuid4())
    stream_started_at = time.monotonic()

    agent = _build_deep_agent(tool_defs)

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
    current_round_reasoning = ""
    current_round_reasoning_started_at: float | None = None
    accumulated_actions: list[ChatAction] = []
    accumulated_tool_result = ToolResult()
    steps: list[StepInfo] = []
    # index(int) → {id, name, args_parts}
    # tool_call_chunk 첫 번째에만 id가 오고 이후엔 None이므로 index를 primary key로 사용
    pending_calls: dict[int, dict] = {}
    emitted_starts: set[int] = set()
    emitted_token_chars = 0
    emitted_reasoning_chars = 0
    tool_message_count = 0

    logger.info(
        f"[coordinator_v3:{request_id}] stream 시작 "
        f"model={settings.coordinator_model} thread_id={thread_id} "
        f"history={len(history[-HISTORY_LIMIT:])} context={_preview_text(context, 500)}\n"
        f"{_fmt_messages(msgs)}"
    )

    try:
        def _append_reasoning(text: str) -> None:
            nonlocal accumulated_reasoning, current_round_reasoning, current_round_reasoning_started_at
            if not text:
                return
            accumulated_reasoning += text
            current_round_reasoning += text
            if current_round_reasoning_started_at is None:
                current_round_reasoning_started_at = time.monotonic()

        async for chunk, metadata in agent.astream(
            {"messages": msgs},
            config={"configurable": {"thread_id": thread_id}},
            stream_mode="messages",
        ):
            node = metadata.get("langgraph_node", "")

            if isinstance(chunk, AIMessageChunk):
                # 1) reasoning (additional_kwargs 방식 - OpenRouter 등)
                ak = chunk.additional_kwargs or {}
                rc = ak.get("reasoning") or ak.get("reasoning_content") or ak.get("thinking") or ""
                if rc:
                    _append_reasoning(rc)
                    emitted_reasoning_chars += len(rc)
                    logger.debug(
                        f"[coordinator_v3:{request_id}] reasoning_chunk source=additional_kwargs "
                        f"node={node} len={len(rc)} preview={_preview_text(rc, 500)}"
                    )
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
                            _append_reasoning(thinking)
                            emitted_reasoning_chars += len(thinking)
                            logger.debug(
                                f"[coordinator_v3:{request_id}] reasoning_chunk source=thinking_block "
                                f"node={node} len={len(thinking)} preview={_preview_text(thinking, 500)}"
                            )
                            yield json.dumps({"type": "reasoning_token", "content": thinking}, ensure_ascii=False)

                    if raw:
                        tag_reasoning, clean = _split_think_content(raw)
                        if tag_reasoning:
                            _append_reasoning(tag_reasoning)
                            emitted_reasoning_chars += len(tag_reasoning)
                            logger.debug(
                                f"[coordinator_v3:{request_id}] reasoning_chunk source=think_tag "
                                f"node={node} len={len(tag_reasoning)} preview={_preview_text(tag_reasoning, 500)}"
                            )
                            yield json.dumps({"type": "reasoning_token", "content": tag_reasoning}, ensure_ascii=False)
                        # tool call 대기 중이 아닐 때만 토큰 전송
                        if clean and not pending_calls:
                            emitted_token_chars += len(clean)
                            logger.debug(
                                f"[coordinator_v3:{request_id}] text_chunk node={node} len={len(clean)} "
                                f"preview={_preview_text(clean, 500)}"
                            )
                            yield json.dumps({"type": "token", "content": clean}, ensure_ascii=False)
                        elif clean:
                            logger.debug(
                                f"[coordinator_v3:{request_id}] text_chunk 보류 node={node} len={len(clean)} "
                                f"pending_calls={len(pending_calls)} preview={_preview_text(clean, 500)}"
                            )

                # 3) tool call 청크 누적
                #    첫 chunk: index=N, id="call_xxx", name="tool_name", args=""
                #    이후 chunk: index=N, id=None, name=None, args="{...}"
                #    → index를 key로 사용해 하나의 entry에 합산
                for tc in chunk.tool_call_chunks or []:
                    idx = tc.get("index") or 0
                    logger.debug(
                        f"[coordinator_v3:{request_id}] tool_call_chunk node={node} idx={idx} "
                        f"id={tc.get('id')} name_part={_preview_text(tc.get('name') or '', 120)} "
                        f"args_part={_preview_text(tc.get('args') or '', 300)}"
                    )
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
                        step_reasoning = current_round_reasoning.strip() or None
                        step_reasoning_duration_ms = None
                        if current_round_reasoning_started_at is not None:
                            step_reasoning_duration_ms = max(
                                1,
                                int((time.monotonic() - current_round_reasoning_started_at) * 1000),
                            )
                        tc["reasoning"] = step_reasoning
                        tc["reasoning_duration_ms"] = step_reasoning_duration_ms
                        emitted_starts.add(idx)
                        logger.info(
                            f"[coordinator_v3:{request_id}] step_start tool={tc['name']} "
                            f"input={_preview_text(''.join(tc['args_parts']), 800)} "
                            f"reasoning_len={len(step_reasoning or '')} "
                            f"reasoning_ms={step_reasoning_duration_ms}"
                        )
                        yield json.dumps({
                            "type": "step_start",
                            "tool": td.label if td else tc["name"],
                            "tool_key": tc["name"],
                            "input": "".join(tc["args_parts"])[:2000],
                            "reasoning": step_reasoning,
                            "reasoning_duration_ms": step_reasoning_duration_ms,
                        }, ensure_ascii=False)
                if not chunk.additional_kwargs and not (chunk.tool_call_chunks or []) and node != "model":
                    logger.debug(
                        f"[coordinator_v3:{request_id}] ai_chunk 수신 node={node} "
                        f"content={_preview_text(chunk.content, 300)}"
                    )

            elif isinstance(chunk, ToolMessage):
                fn_name = chunk.name or ""
                output = chunk.content if isinstance(chunk.content, str) else json.dumps(chunk.content)
                td = tools_by_name.get(fn_name)
                tool_message_count += 1
                logger.debug(
                    f"[coordinator_v3:{request_id}] tool_message #{tool_message_count} "
                    f"tool={fn_name} call_id={chunk.tool_call_id} output_len={len(output)} "
                    f"output={_preview_text(output, 800)}"
                )

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
                step_reasoning = None
                if key_to_remove is not None:
                    call_info = pending_calls.pop(key_to_remove)
                    args_str = "".join(call_info["args_parts"])
                    step_reasoning = call_info.get("reasoning")
                    if not pending_calls:
                        emitted_starts.clear()
                        current_round_reasoning = ""
                        current_round_reasoning_started_at = None

                steps.append(StepInfo(
                    tool=td.label if td else fn_name,
                    tool_key=fn_name,
                    input=args_str[:2000],
                    output=summary,
                    reasoning=step_reasoning,
                ))
                logger.info(
                    f"[coordinator_v3:{request_id}] step_end tool={fn_name} "
                    f"summary={_preview_text(summary, 500)} actions={len(actions)} "
                    f"tool_result={'yes' if tool_result else 'no'}"
                )
                yield json.dumps({"type": "step_end", "tool_key": fn_name, "output": summary}, ensure_ascii=False)
            else:
                logger.info(
                    f"[coordinator_v3:{request_id}] 알 수 없는 chunk type={type(chunk).__name__} "
                    f"node={node}"
                )

        final_reasoning = current_round_reasoning.strip() or None
        final_reasoning_duration_ms = None
        if current_round_reasoning_started_at is not None:
            final_reasoning_duration_ms = max(
                1,
                int((time.monotonic() - current_round_reasoning_started_at) * 1000),
            )
        total_elapsed_ms = (time.monotonic() - stream_started_at) * 1000
        logger.info(
            f"[coordinator_v3:{request_id}] done steps={len(steps)} actions={len(accumulated_actions)} "
            f"token_chars={emitted_token_chars} reasoning_chars={emitted_reasoning_chars} "
            f"final_reasoning_len={len(final_reasoning or '')} elapsed_ms={total_elapsed_ms:.1f}"
        )
        yield json.dumps({
            "type": "done",
            "actions": [a.model_dump() for a in accumulated_actions],
            "tool_results": accumulated_tool_result.model_dump(),
            "steps": [s.model_dump() for s in steps],
            "reasoning": final_reasoning,
            "reasoning_duration_ms": final_reasoning_duration_ms,
        }, ensure_ascii=False)

    except Exception as e:
        logger.error(f"stream_coordinator(v3) 오류: {e}", exc_info=True)
        yield json.dumps({"type": "error", "content": str(e)}, ensure_ascii=False)
    finally:
        total_elapsed_ms = (time.monotonic() - stream_started_at) * 1000
        logger.info(
            f"[coordinator_v3:{request_id}] stream 종료 elapsed_ms={total_elapsed_ms:.1f} "
            f"steps={len(steps)} tool_messages={tool_message_count}"
        )


async def run_coordinator(
    message: str,
    history: list[dict] = [],
    context: dict = {},
) -> ChatResponse:
    """비스트리밍 실행."""
    started_at = time.monotonic()
    logger.info(
        f"[coordinator_v3.run] 시작 history={len(history)} context={_preview_text(context, 500)} "
        f"message={_preview_text(message, 500)}"
    )
    tokens: list[str] = []
    all_actions: list[ChatAction] = []
    tool_result = ToolResult()
    steps: list[StepInfo] = []
    final_reasoning: str | None = None

    try:
        async for raw in stream_coordinator(message, history, context):
            event = json.loads(raw)
            t = event.get("type")
            if t == "token":
                tokens.append(event["content"])
            elif t == "done":
                all_actions = [ChatAction(**a) for a in event.get("actions", [])]
                tr = event.get("tool_results", {})
                tool_result = ToolResult(**tr) if tr else ToolResult()
                steps = [StepInfo(**s) for s in event.get("steps", [])]
                final_reasoning = event.get("reasoning")
                logger.info(
                    f"[coordinator_v3.run] done message_len={sum(len(t) for t in tokens)} "
                    f"steps={len(steps)} actions={len(all_actions)} "
                    f"final_reasoning_len={len(final_reasoning or '')}"
                )
                break
            elif t == "error":
                logger.warning(
                    f"[coordinator_v3.run] error event={_preview_text(event.get('content', ''), 500)}"
                )
                return ChatResponse(message=f"오류: {event.get('content', '')}")
    except Exception as e:
        logger.error(f"run_coordinator(v3) 실패: {e}", exc_info=True)
        return ChatResponse(message=f"처리 중 오류가 발생했습니다: {str(e)}")
    finally:
        elapsed_ms = (time.monotonic() - started_at) * 1000
        logger.info(f"[coordinator_v3.run] 종료 elapsed_ms={elapsed_ms:.1f}")

    return ChatResponse(
        message="".join(tokens) or "처리가 완료되었습니다.",
        actions=all_actions,
        tool_results=tool_result,
        steps=steps,
        reasoning=final_reasoning,
    )
