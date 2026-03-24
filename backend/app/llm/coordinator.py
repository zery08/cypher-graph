"""
Coordinator - raw OpenAI 클라이언트 기반 agent loop
native tool calling 을 먼저 시도하고, 모델이 지원하지 않으면
텍스트 기반 tool calling (JSON 파싱) 으로 자동 fallback 한다.
GLM 4.7 / LFM thinking 모드 등 reasoning_content 를 별도 필드로 분리한다.
"""
import asyncio
import json
import logging
import re
from datetime import datetime
from typing import AsyncGenerator

from openai import AsyncOpenAI, NotFoundError, BadRequestError
from app.core.config import settings
from app.llm.prompts import COORDINATOR_SYSTEM_PROMPT
from app.llm.tools import load_all_tools, ToolDef
from app.schemas.chat import ChatResponse, ChatAction, ToolResult, StepInfo

logger = logging.getLogger(__name__)

MAX_TOOL_ROUNDS = 6


# ── 클라이언트 / 프롬프트 ──────────────────────────────────────────────────────

def _make_client() -> AsyncOpenAI:
    return AsyncOpenAI(
        api_key=settings.coordinator_api_key,
        base_url=settings.coordinator_base_url,
    )


def _thinking_extra_body() -> dict:
    """
    OpenRouter reasoning / thinking 파라미터를 구성한다.
    - COORDINATOR_REASONING_EFFORT=high  → {"reasoning": {"effort": "high"}}
    - COORDINATOR_THINKING_BUDGET=8000   → {"thinking": {"type": "enabled", "budget_tokens": 8000}}
    둘 다 비어있으면 빈 dict 반환 (기본 동작).
    """
    extra: dict = {}
    if settings.coordinator_reasoning_effort:
        extra["reasoning"] = {"effort": settings.coordinator_reasoning_effort}
    if settings.coordinator_thinking_budget > 0:
        extra["thinking"] = {
            "type": "enabled",
            "budget_tokens": settings.coordinator_thinking_budget,
        }
    return extra


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


def _system_prompt(tool_defs: list[ToolDef], *, text_mode: bool = False) -> str:
    base = COORDINATOR_SYSTEM_PROMPT.format(
        current_date=datetime.now().strftime("%Y-%m-%d"),
        schema=_schema_snippet(),
    )
    if not text_mode:
        return base

    # text_mode: tool spec 을 프롬프트에 직접 포함하고 JSON 출력 규칙을 안내한다
    tool_desc_lines = ["## 사용 가능한 Tool (JSON 형식으로 호출)"]
    for t in tool_defs:
        fn = t.spec["function"]
        params = fn.get("parameters", {}).get("properties", {})
        param_str = ", ".join(
            f'{k}: {v.get("type","string")} — {v.get("description","")}'
            for k, v in params.items()
        )
        tool_desc_lines.append(f'- **{t.name}**: {fn["description"]}')
        if param_str:
            tool_desc_lines.append(f'  인자: {param_str}')

    tool_block = "\n".join(tool_desc_lines)

    rule_block = """
## Tool 호출 규칙
Tool 을 호출할 때는 반드시 아래 형식의 JSON 블록만 출력하고 다른 텍스트는 붙이지 않는다.
필요하면 이 블록을 여러 개 연속으로 출력할 수 있다.
```tool_call
{"name": "<tool_name>", "arguments": {<인자 JSON>}}
```
Tool 결과를 받은 뒤 최종 답변을 한글로 작성한다.
Tool 이 필요 없을 경우 바로 한글로 답변한다.
"""
    return f"{base}\n\n{tool_block}\n{rule_block}"


def _build_messages(history: list[dict], context: dict, message: str) -> list[dict]:
    msgs: list[dict] = []
    for m in history[-6:]:
        msgs.append({"role": m["role"], "content": m["content"]})
    prefix = ""
    if context.get("current_query"):
        prefix += f"[현재 실행 쿼리: {context['current_query']}]\n"
    if context.get("selected_node"):
        prefix += f"[선택된 노드: {context['selected_node']}]\n"
    msgs.append({"role": "user", "content": f"{prefix}{message}" if prefix else message})
    return msgs


# ── reasoning 추출 ─────────────────────────────────────────────────────────────

def _extract_reasoning(message) -> str:
    extra = getattr(message, "model_extra", {}) or {}
    rc = extra.get("reasoning_content") or extra.get("thinking") or ""
    if rc:
        return rc
    content = getattr(message, "content", None)
    if isinstance(content, list):
        parts = [b.get("thinking", "") for b in content
                 if isinstance(b, dict) and b.get("type") == "thinking"]
        return "\n".join(parts)
    return ""


def _extract_reasoning_from_delta(delta) -> str:
    extra = getattr(delta, "model_extra", {}) or {}
    return extra.get("reasoning") or extra.get("reasoning_content") or extra.get("thinking") or ""


_THINK_TAG_RE = re.compile(r"<think>(.*?)</think>", re.DOTALL)


def _split_think_content(text: str) -> tuple[str, str]:
    """
    <think>...</think> 태그를 content에서 분리한다.
    QwQ, DeepSeek-R1 계열은 reasoning을 별도 필드 대신 이 태그로 감싼다.
    returns: (reasoning, clean_content)
    """
    reasoning_parts = _THINK_TAG_RE.findall(text)
    clean = _THINK_TAG_RE.sub("", text).strip()
    return "\n".join(reasoning_parts).strip(), clean


# ── tool 결과 파싱 ─────────────────────────────────────────────────────────────

def _parse_tool_result(tool_name: str, output: str) -> tuple[ToolResult | None, list[ChatAction], str]:
    actions: list[ChatAction] = []
    summary = output[:2000]
    try:
        data = json.loads(output)
        if "error" in data:
            return None, [], f"오류: {data['error']}"
        if tool_name in ("graph_cypher_qa_tool", "graph_query_tool"):
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
            if cypher:
                summary += f"\n```cypher\n{cypher}\n```"
                actions.append(ChatAction(type="apply_query", query=cypher))
            # 노드가 하나라도 있으면 그래프 탭, 없으면 테이블 탭
            if data.get("nodes"):
                actions.append(ChatAction(type="open_tab", tab="graph"))
            else:
                actions.append(ChatAction(type="open_tab", tab="table"))
            return result, actions, summary
        if tool_name == "table_summary_tool":
            columns = data.get("columns", [])
            numeric_stats = data.get("numeric_stats", {})
            summary = (
                f"표 요약: {data.get('row_count', '?')}행, "
                f"컬럼 {len(columns)}개"
            )
            if columns:
                summary += f" ({', '.join(columns[:5])})"
            if numeric_stats:
                summary += f", 수치 컬럼 {len(numeric_stats)}개"
            return ToolResult(summary=summary), actions, summary
        if tool_name == "chart_recommendation_tool":
            chart_type = data.get("chart_type", "line")
            reason = data.get("reason", "")
            raw_config = data.get("config") or {}
            chart_config = {"chartType": chart_type, **raw_config}
            if raw_config.get("xAxis") and not chart_config.get("xKey"):
                chart_config["xKey"] = raw_config["xAxis"]
            if raw_config.get("yAxis") and not chart_config.get("yKey"):
                chart_config["yKey"] = raw_config["yAxis"]
            summary = f"차트 추천: {chart_type}"
            if reason:
                summary += f" - {reason}"
            actions.append(ChatAction(type="open_tab", tab="chart"))
            return ToolResult(chart=chart_config, summary=summary), actions, summary
    except Exception:
        pass
    return None, [], summary


# ── 텍스트 기반 tool call 파싱 ─────────────────────────────────────────────────

_TOOL_CALL_RE = re.compile(
    r"```tool_calls?\s*\n(.*?)\n```",
    re.DOTALL | re.IGNORECASE,
)


def _parse_text_tool_calls(text: str) -> list[dict]:
    """LLM 텍스트 응답에서 하나 이상의 ```tool_call ... ``` 블록을 파싱한다."""
    tool_calls: list[dict] = []
    for m in _TOOL_CALL_RE.finditer(text):
        try:
            payload = json.loads(m.group(1).strip())
        except Exception:
            continue
        if isinstance(payload, dict):
            tool_calls.append(payload)
        elif isinstance(payload, list):
            tool_calls.extend(item for item in payload if isinstance(item, dict))
    return tool_calls


def _strip_tool_call_block(text: str) -> str:
    return _TOOL_CALL_RE.sub("", text).strip()


# ── 공통 tool 실행 ─────────────────────────────────────────────────────────────

def _run_tool(tool_def: ToolDef | None, fn_name: str, fn_args_str: str) -> str:
    if tool_def is None:
        return json.dumps({"error": f"알 수 없는 tool: {fn_name}"})
    try:
        args = json.loads(fn_args_str) if isinstance(fn_args_str, str) else fn_args_str
        return tool_def.run(args)
    except Exception as e:
        logger.error(f"tool 실행 오류 ({fn_name}): {e}")
        return json.dumps({"error": str(e)})


async def _run_tool_batch(
    tool_calls: list[tuple[ToolDef | None, str, str | dict]],
) -> list[tuple[str, ToolResult | None, list[ChatAction], str]]:
    async def _execute_one(
        tool_def: ToolDef | None,
        fn_name: str,
        fn_args: str | dict,
    ) -> tuple[str, ToolResult | None, list[ChatAction], str]:
        output = await asyncio.to_thread(_run_tool, tool_def, fn_name, fn_args)
        tool_result, actions, summary = _parse_tool_result(fn_name, output)
        return output, tool_result, actions, summary

    return await asyncio.gather(
        *[_execute_one(tool_def, fn_name, fn_args) for tool_def, fn_name, fn_args in tool_calls]
    )


def _merge_actions(existing: list[ChatAction], incoming: list[ChatAction]) -> list[ChatAction]:
    merged = list(existing)
    seen = {json.dumps(action.model_dump(), sort_keys=True, ensure_ascii=False) for action in existing}
    for action in incoming:
        key = json.dumps(action.model_dump(), sort_keys=True, ensure_ascii=False)
        if key not in seen:
            merged.append(action)
            seen.add(key)
    return merged


def _merge_tool_result(base: ToolResult, incoming: ToolResult | None) -> ToolResult:
    if incoming is None:
        return base

    merged = base.model_copy(deep=True)

    if incoming.graph is not None:
        merged.graph = incoming.graph
    if incoming.table is not None:
        merged.table = incoming.table
    if incoming.chart is not None:
        merged.chart = incoming.chart
    if incoming.cypher:
        merged.cypher = incoming.cypher

    if incoming.summary:
        if merged.summary:
            summaries = [part.strip() for part in [merged.summary, incoming.summary] if part.strip()]
            deduped: list[str] = []
            for part in summaries:
                if part not in deduped:
                    deduped.append(part)
            merged.summary = "\n".join(deduped)
        else:
            merged.summary = incoming.summary

    return merged


# ── Native tool calling ────────────────────────────────────────────────────────

async def _stream_native(
    client: AsyncOpenAI,
    tools_by_name: dict[str, ToolDef],
    tool_specs: list[dict],
    messages: list[dict],
) -> AsyncGenerator[str, None]:
    """native tool calling 스트림. NotFoundError / BadRequestError 시 StopAsyncIteration."""
    steps: list[StepInfo] = []
    all_actions: list[ChatAction] = []
    final_tool_result = ToolResult()
    accumulated_reasoning = ""

    for _ in range(MAX_TOOL_ROUNDS):
        stream = await client.chat.completions.create(
            model=settings.coordinator_model,
            messages=messages,
            tools=tool_specs,
            tool_choice="auto",
            stream=True,
            max_tokens=settings.coordinator_max_tokens,
            extra_body=_thinking_extra_body() or None,
        )

        content_parts: list[str] = []
        reasoning_parts: list[str] = []
        tool_calls_acc: dict[int, dict] = {}

        def _fmt_messages(msgs: list[dict]) -> str:
            lines = []
            for m in msgs:
                role = m.get("role", "").upper()
                content = str(m.get("content") or "")
                reasoning = (m.get("model_extra") or {}).get("reasoning", "")
                if reasoning:
                    lines.append(f"  [REASONING] {reasoning[:500]}")
                lines.append(f"  [{role}] {content[:500]}")
            return "\n".join(lines)

        logger.info(f"[LLM 요청] model={settings.coordinator_model}\n{_fmt_messages(messages)}")

        async for chunk in stream:
            if not chunk.choices:
                continue
            choice = chunk.choices[0]
            delta = choice.delta

            # delta.model_extra["reasoning"] 추출 (qwen/qwq, gemini thinking 등)
            delta_extra = getattr(delta, "model_extra", {}) or {}
            rc = (
                delta_extra.get("reasoning")
                or delta_extra.get("reasoning_content")
                or delta_extra.get("thinking")
                or ""
            )
            if rc:
                reasoning_parts.append(rc)
                accumulated_reasoning += rc
                yield json.dumps({"type": "reasoning_token", "content": rc}, ensure_ascii=False)

            if delta.content:
                content_parts.append(delta.content)
                if not tool_calls_acc:
                    yield json.dumps({"type": "token", "content": delta.content}, ensure_ascii=False)

            if delta.tool_calls:
                for tc in delta.tool_calls:
                    idx = tc.index
                    if idx not in tool_calls_acc:
                        tool_calls_acc[idx] = {"id": "", "type": "function",
                                               "function": {"name": "", "arguments": ""}}
                    if tc.id:
                        tool_calls_acc[idx]["id"] = tc.id
                    if tc.function:
                        if tc.function.name:
                            tool_calls_acc[idx]["function"]["name"] += tc.function.name
                        if tc.function.arguments:
                            tool_calls_acc[idx]["function"]["arguments"] += tc.function.arguments

        full_content = "".join(content_parts)

        # reasoning_content 필드 방식 (GLM 등) + <think> 태그 방식 (QwQ, DeepSeek-R1) 동시 지원
        tag_reasoning, clean_content = _split_think_content(full_content)
        full_reasoning = ("".join(reasoning_parts) + "\n" + tag_reasoning).strip()
        if tag_reasoning:
            full_content = clean_content
            accumulated_reasoning = ("".join(
                [accumulated_reasoning] + [tag_reasoning]
            )).strip()

        step_reasoning = full_reasoning or None

        tool_names = [tc["function"]["name"] for tc in tool_calls_acc.values()]
        log_lines = [
            f"[LLM 응답] reasoning={len(full_reasoning)}자 | content={len(full_content)}자 | tool_calls={tool_names}",
        ]
        if full_reasoning:
            log_lines.append(f"  [REASONING]\n{full_reasoning}")
        if full_content:
            log_lines.append(f"  [ASSISTANT]\n{full_content}")
        for tc in tool_calls_acc.values():
            log_lines.append(f"  [TOOL_CALL] {tc['function']['name']}({tc['function']['arguments'][:300]})")
        logger.info("\n".join(log_lines))

        # <think> 태그에서 분리한 reasoning을 reasoning_token 이벤트로 전송
        if tag_reasoning:
            yield json.dumps({"type": "reasoning_token", "content": tag_reasoning}, ensure_ascii=False)

        if not tool_calls_acc:
            yield json.dumps({
                "type": "done",
                "actions": [a.model_dump() for a in all_actions],
                "tool_results": final_tool_result.model_dump(),
                "steps": [s.model_dump() for s in steps],
                "reasoning": accumulated_reasoning.strip() or None,
            }, ensure_ascii=False)
            return

        tool_calls_list = [tool_calls_acc[i] for i in sorted(tool_calls_acc)]
        messages.append({"role": "assistant", "content": full_content or None,
                         "tool_calls": tool_calls_list})

        batch_inputs: list[tuple[ToolDef | None, str, str]] = []
        for tc in tool_calls_list:
            fn_name = tc["function"]["name"]
            fn_args_str = tc["function"]["arguments"]
            tool_def = tools_by_name.get(fn_name)

            yield json.dumps({
                "type": "step_start",
                "tool": tool_def.label if tool_def else fn_name,
                "tool_key": fn_name,
                "input": fn_args_str[:2000],
                "reasoning": step_reasoning,
            }, ensure_ascii=False)

            batch_inputs.append((tool_def, fn_name, fn_args_str))

        batch_results = await _run_tool_batch(batch_inputs)

        for tc, (output, tool_result, actions, summary) in zip(tool_calls_list, batch_results):
            fn_name = tc["function"]["name"]
            fn_args_str = tc["function"]["arguments"]
            tool_def = tools_by_name.get(fn_name)
            if tool_result:
                final_tool_result = _merge_tool_result(final_tool_result, tool_result)
            all_actions = _merge_actions(all_actions, actions)

            steps.append(StepInfo(
                tool=tool_def.label if tool_def else fn_name,
                tool_key=fn_name,
                input=fn_args_str[:2000],
                output=summary,
                reasoning=step_reasoning,
            ))

            yield json.dumps({"type": "step_end", "tool_key": fn_name,
                              "output": summary}, ensure_ascii=False)

            messages.append({"role": "tool", "tool_call_id": tc["id"], "content": output})

    yield json.dumps({"type": "error", "content": "최대 tool 호출 횟수를 초과했습니다."}, ensure_ascii=False)


# ── 텍스트 기반 tool calling (fallback) ───────────────────────────────────────

async def _stream_text(
    client: AsyncOpenAI,
    tools_by_name: dict[str, ToolDef],
    tool_defs: list[ToolDef],
    messages: list[dict],
) -> AsyncGenerator[str, None]:
    """
    tool use 미지원 모델 fallback.
    시스템 프롬프트에 tool spec 을 넣고 LLM 이 ```tool_call``` 블록으로 호출하도록 한다.
    """
    steps: list[StepInfo] = []
    all_actions: list[ChatAction] = []
    final_tool_result = ToolResult()
    accumulated_reasoning = ""

    # 시스템 메시지를 text_mode 버전으로 교체
    messages[0] = {"role": "system",
                   "content": _system_prompt(tool_defs, text_mode=True)}

    for _ in range(MAX_TOOL_ROUNDS):
        stream = await client.chat.completions.create(
            model=settings.coordinator_model,
            messages=messages,
            stream=True,
            max_tokens=settings.coordinator_max_tokens,
            extra_body=_thinking_extra_body() or None,
        )

        content_parts: list[str] = []
        reasoning_parts: list[str] = []

        async for chunk in stream:
            delta = chunk.choices[0].delta if chunk.choices else None
            if delta is None:
                continue

            rc = _extract_reasoning_from_delta(delta)
            if rc:
                reasoning_parts.append(rc)
                accumulated_reasoning += rc
                yield json.dumps({"type": "reasoning_token", "content": rc}, ensure_ascii=False)

            if delta.content:
                content_parts.append(delta.content)

        full_content = "".join(content_parts)
        step_reasoning = "".join(reasoning_parts) or None

        tool_calls = _parse_text_tool_calls(full_content)

        if not tool_calls:
            # tool call 없음 → 최종 답변
            answer = _strip_tool_call_block(full_content)
            for char in answer:
                yield json.dumps({"type": "token", "content": char}, ensure_ascii=False)
            yield json.dumps({
                "type": "done",
                "actions": [a.model_dump() for a in all_actions],
                "tool_results": final_tool_result.model_dump(),
                "steps": [s.model_dump() for s in steps],
                "reasoning": accumulated_reasoning.strip() or None,
            }, ensure_ascii=False)
            return

        # 대화 히스토리에 tool call + result 추가
        messages.append({"role": "assistant", "content": full_content})
        tool_feedback_blocks: list[str] = []
        batch_inputs: list[tuple[ToolDef | None, str, dict]] = []

        for tc_data in tool_calls:
            fn_name = tc_data.get("name", "")
            fn_args = tc_data.get("arguments", {})
            fn_args_str = json.dumps(fn_args, ensure_ascii=False)
            tool_def = tools_by_name.get(fn_name)

            yield json.dumps({
                "type": "step_start",
                "tool": tool_def.label if tool_def else fn_name,
                "tool_key": fn_name,
                "input": fn_args_str[:2000],
                "reasoning": step_reasoning,
            }, ensure_ascii=False)

            batch_inputs.append((tool_def, fn_name, fn_args))

        batch_results = await _run_tool_batch(batch_inputs)

        for tc_data, (output, tool_result, actions, summary) in zip(tool_calls, batch_results):
            fn_name = tc_data.get("name", "")
            fn_args = tc_data.get("arguments", {})
            fn_args_str = json.dumps(fn_args, ensure_ascii=False)
            tool_def = tools_by_name.get(fn_name)
            if tool_result:
                final_tool_result = _merge_tool_result(final_tool_result, tool_result)
            all_actions = _merge_actions(all_actions, actions)

            steps.append(StepInfo(
                tool=tool_def.label if tool_def else fn_name,
                tool_key=fn_name,
                input=fn_args_str[:2000],
                output=summary,
                reasoning=step_reasoning,
            ))

            yield json.dumps({"type": "step_end", "tool_key": fn_name,
                              "output": summary}, ensure_ascii=False)
            tool_feedback_blocks.append(f"[tool_result: {fn_name}]\n{output}")

        messages.append({
            "role": "user",
            "content": (
                "\n\n".join(tool_feedback_blocks)
                + "\n\n위 결과를 종합해서 필요하면 추가로 tool을 호출하고, 아니면 한글로 최종 답변해주세요."
            ),
        })

    yield json.dumps({"type": "error", "content": "최대 tool 호출 횟수를 초과했습니다."}, ensure_ascii=False)


# ── 공개 API ──────────────────────────────────────────────────────────────────

async def stream_coordinator(
    message: str,
    history: list[dict] = [],
    context: dict = {},
) -> AsyncGenerator[str, None]:
    """
    coordinator 스트리밍 실행.
    native tool calling → 실패 시 text-based fallback 자동 전환.
    """
    client = _make_client()
    tool_defs = load_all_tools()
    tools_by_name = {t.name: t for t in tool_defs}
    tool_specs = [t.spec for t in tool_defs]

    messages: list[dict] = [
        {"role": "system", "content": _system_prompt(tool_defs, text_mode=False)}
    ]
    messages.extend(_build_messages(history, context, message))

    try:
        # native tool calling 시도
        async for event in _stream_native(client, tools_by_name, tool_specs, messages):
            yield event

    except (NotFoundError, BadRequestError) as e:
        err_msg = str(e)
        if "tool" in err_msg.lower() or "404" in err_msg:
            logger.warning(f"native tool calling 미지원, text fallback 전환: {e}")
            yield json.dumps({"type": "fallback", "content": "text-based tool calling 모드로 전환합니다."}, ensure_ascii=False)
            # messages 재구성 (system 은 _stream_text 내부에서 교체됨)
            messages_fallback: list[dict] = [
                {"role": "system", "content": ""}  # placeholder
            ]
            messages_fallback.extend(_build_messages(history, context, message))
            async for event in _stream_text(client, tools_by_name, tool_defs, messages_fallback):
                yield event
        else:
            logger.error(f"stream_coordinator 오류: {e}", exc_info=True)
            yield json.dumps({"type": "error", "content": str(e)}, ensure_ascii=False)

    except Exception as e:
        logger.error(f"stream_coordinator 오류: {e}", exc_info=True)
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
        logger.error(f"run_coordinator 실패: {e}", exc_info=True)
        return ChatResponse(message=f"처리 중 오류가 발생했습니다: {str(e)}")

    return ChatResponse(
        message="".join(tokens) or "처리가 완료되었습니다.",
        actions=all_actions,
        tool_results=final_tool_result,
        steps=steps,
        reasoning="".join(reasoning_parts).strip() or None,
    )
