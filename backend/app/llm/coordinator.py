"""
Coordinator LLM - OpenAI 호환 수동 agent loop 기반 tool 실행 및 스트리밍
"""
import json
import logging
from datetime import datetime
from typing import Any, AsyncGenerator

from openai import OpenAI
from langchain_core.utils.function_calling import convert_to_openai_tool

from app.core.config import settings
from app.llm.prompts import COORDINATOR_SYSTEM_PROMPT
from app.llm.tools.graph_schema_tool import graph_schema_tool
from app.llm.tools.graph_cypher_tool import graph_cypher_qa_tool, graph_query_tool
from app.llm.tools.utility_tools import table_summary_tool, chart_recommendation_tool
from app.schemas.chat import ChatResponse, ChatAction, ToolResult, StepInfo

logger = logging.getLogger(__name__)

AVAILABLE_TOOL_LIST = [
    graph_schema_tool,
    graph_cypher_qa_tool,
    graph_query_tool,
    table_summary_tool,
    chart_recommendation_tool,
]
AVAILABLE_TOOLS = {tool.name: tool for tool in AVAILABLE_TOOL_LIST}

TOOL_LABELS = {
    "graph_schema_tool": "스키마 조회",
    "graph_cypher_qa_tool": "Cypher 생성 및 실행",
    "graph_query_tool": "Cypher 직접 실행",
    "table_summary_tool": "데이터 요약",
    "chart_recommendation_tool": "차트 추천",
}

OPENAI_TOOLS = [convert_to_openai_tool(tool) for tool in AVAILABLE_TOOL_LIST]


def _make_client() -> OpenAI:
    return OpenAI(
        api_key=settings.coordinator_api_key or "dummy",
        base_url=settings.coordinator_base_url or None,
    )


def _build_messages(history: list[dict], context: dict, message: str) -> list[dict[str, Any]]:
    messages: list[dict[str, Any]] = [
        {
            "role": "system",
            "content": COORDINATOR_SYSTEM_PROMPT.format(current_date=datetime.now().strftime("%Y-%m-%d")),
        }
    ]
    for msg in history[-6:]:
        messages.append({"role": msg["role"], "content": msg["content"]})

    context_prefix = ""
    if context.get("current_query"):
        context_prefix += f"[현재 실행 쿼리: {context['current_query']}]\n"
    if context.get("selected_node"):
        context_prefix += f"[선택된 노드: {context['selected_node']}]\n"

    user_text = f"{context_prefix}{message}" if context_prefix else message
    messages.append({"role": "user", "content": user_text})
    return messages


def _parse_tool_calls_from_stream(stream: Any) -> tuple[str, str, list[dict[str, Any]], list[dict[str, Any]]]:
    reasoning = ""
    content = ""
    assembled: dict[int, dict[str, Any]] = {}
    events: list[dict[str, Any]] = []
    for chunk in stream:
        delta = chunk.choices[0].delta
        thinking_piece = getattr(delta, "reasoning_content", None)
        if thinking_piece:
            reasoning += thinking_piece
            events.append({"type": "thinking_token", "content": thinking_piece})
        token_piece = getattr(delta, "content", None)
        if token_piece:
            content += token_piece
            events.append({"type": "token", "content": token_piece})
        for tc in getattr(delta, "tool_calls", None) or []:
            idx = tc.index or 0
            entry = assembled.setdefault(idx, {"id": "", "type": "function", "function": {"name": "", "arguments": ""}})
            if tc.id:
                entry["id"] = tc.id
            if tc.function:
                if tc.function.name:
                    entry["function"]["name"] += tc.function.name
                if tc.function.arguments:
                    entry["function"]["arguments"] += tc.function.arguments

    tool_calls = [assembled[k] for k in sorted(assembled.keys())]
    return reasoning, content, tool_calls, events


def _run_tool_call(tc: dict[str, Any]) -> tuple[str, ToolResult | None, list[ChatAction], str]:
    name = tc["function"]["name"]
    args_str = tc["function"].get("arguments") or "{}"
    try:
        args = json.loads(args_str)
    except json.JSONDecodeError:
        args = {}

    tool = AVAILABLE_TOOLS.get(name)
    if tool is None:
        result = json.dumps({"error": f"unknown tool: {name}"}, ensure_ascii=False)
        return result, None, [], result

    output = tool.invoke(args)
    output_str = output if isinstance(output, str) else json.dumps(output, ensure_ascii=False)
    tool_result, actions, summary = _extract_tool_result(name, output_str)
    return output_str, tool_result, actions, summary


def _extract_tool_result(tool_name: str, output_str: str) -> tuple[ToolResult | None, list[ChatAction], str]:
    actions: list[ChatAction] = []
    summary = output_str[:2000]
    try:
        data = json.loads(output_str)
        if "error" in data:
            return None, [], f"오류: {data['error']}"

        result = ToolResult()
        if tool_name in ("graph_cypher_qa_tool", "graph_query_tool"):
            result.cypher = data.get("cypher", "")
            result.graph = {
                "nodes": data.get("nodes", []),
                "edges": data.get("edges", []),
                "raw": data.get("result", data.get("raw", [])),
            }
            result.table = data.get("result", data.get("raw", []))
            result.summary = data.get("answer", "")
            row_count = data.get("row_count", "?")
            cypher = data.get("cypher", "")
            summary = f"{row_count}건 반환"
            if cypher:
                summary += f"\n```cypher\n{cypher}\n```"
            if data.get("cypher"):
                actions.append(ChatAction(type="apply_query", query=data["cypher"]))
            if data.get("nodes"):
                actions.append(ChatAction(type="open_tab", tab="graph"))
            elif data.get("result"):
                actions.append(ChatAction(type="open_tab", tab="table"))
        return result, actions, summary
    except Exception as e:
        logger.warning(f"_extract_tool_result 파싱 실패 ({tool_name}): {e} | 입력 앞부분: {output_str[:100]}")
        return None, [], summary


async def run_coordinator(
    message: str,
    history: list[dict] = [],
    context: dict = {},
) -> ChatResponse:
    try:
        client = _make_client()
        messages = _build_messages(history, context, message)
        steps: list[StepInfo] = []
        all_actions: list[ChatAction] = []
        final_tool_result = ToolResult()
        final_answer = ""
        thinking_parts: list[str] = []

        for _ in range(8):
            resp = client.chat.completions.create(
                model=settings.coordinator_model,
                messages=messages,
                tools=OPENAI_TOOLS,
                extra_body={"thinking": {"type": "enabled", "clear_thinking": False}},
            )
            msg = resp.choices[0].message
            answer_piece = msg.content or ""
            reasoning_piece = getattr(msg, "reasoning_content", None) or ""
            tool_calls = [tc.model_dump() for tc in (msg.tool_calls or [])]
            final_answer = answer_piece or final_answer
            if reasoning_piece:
                thinking_parts.append(reasoning_piece)

            if not tool_calls:
                break

            messages.append({
                "role": "assistant",
                "content": answer_piece,
                "reasoning_content": reasoning_piece,
                "tool_calls": tool_calls,
            })

            for tc in tool_calls:
                output_str, tool_result, actions, summary = _run_tool_call(tc)
                tool_name = tc["function"]["name"]
                input_preview = (tc["function"].get("arguments") or "")[:2000]
                steps.append(StepInfo(tool=TOOL_LABELS.get(tool_name, tool_name), tool_key=tool_name, input=input_preview, output=summary))
                if tool_result:
                    final_tool_result = tool_result
                    all_actions.extend(actions)
                messages.append({"role": "tool", "tool_call_id": tc["id"], "content": output_str})

        return ChatResponse(
            message=final_answer or "처리가 완료되었습니다.",
            actions=all_actions,
            tool_results=final_tool_result,
            steps=steps,
            thinking="".join(thinking_parts) or None,
        )

    except Exception as e:
        logger.error(f"coordinator 실행 실패: {e}", exc_info=True)
        return ChatResponse(message=f"처리 중 오류가 발생했습니다: {str(e)}", actions=[], tool_results=ToolResult())


async def stream_coordinator(
    message: str,
    history: list[dict] = [],
    context: dict = {},
) -> AsyncGenerator[str, None]:
    client = _make_client()
    messages = _build_messages(history, context, message)
    steps: list[StepInfo] = []
    all_actions: list[ChatAction] = []
    final_tool_result = ToolResult()
    collected_thinking: list[str] = []

    try:
        for _ in range(8):
            stream = client.chat.completions.create(
                model=settings.coordinator_model,
                messages=messages,
                tools=OPENAI_TOOLS,
                stream=True,
                extra_body={"thinking": {"type": "enabled", "clear_thinking": False}},
            )
            reasoning, content, tool_calls, events = _parse_tool_calls_from_stream(stream)
            for event in events:
                if event["type"] == "thinking_token":
                    collected_thinking.append(event["content"])
                yield json.dumps(event, ensure_ascii=False)

            if not tool_calls:
                break

            messages.append({
                "role": "assistant",
                "content": content,
                "reasoning_content": reasoning,
                "tool_calls": tool_calls,
            })

            for tc in tool_calls:
                tool_name = tc["function"]["name"]
                input_preview = (tc["function"].get("arguments") or "")[:2000]
                yield json.dumps({
                    "type": "step_start",
                    "tool": TOOL_LABELS.get(tool_name, tool_name),
                    "tool_key": tool_name,
                    "input": input_preview,
                }, ensure_ascii=False)

                output_str, tool_result, actions, summary = _run_tool_call(tc)
                steps.append(StepInfo(tool=TOOL_LABELS.get(tool_name, tool_name), tool_key=tool_name, input=input_preview, output=summary))
                if tool_result:
                    final_tool_result = tool_result
                    all_actions.extend(actions)

                yield json.dumps({"type": "step_end", "tool_key": tool_name, "output": summary}, ensure_ascii=False)
                messages.append({"role": "tool", "tool_call_id": tc["id"], "content": output_str})

        yield json.dumps({
            "type": "done",
            "actions": [a.model_dump() for a in all_actions],
            "tool_results": final_tool_result.model_dump(),
            "steps": [s.model_dump() for s in steps],
            "thinking": "".join(collected_thinking) or None,
        }, ensure_ascii=False)

    except Exception as e:
        logger.error(f"stream_coordinator 오류: {e}", exc_info=True)
        yield json.dumps({"type": "error", "content": str(e)}, ensure_ascii=False)
