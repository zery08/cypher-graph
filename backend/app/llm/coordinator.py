"""
Coordinator LLM - tool 선택 및 최종 답변 생성 (LangChain 1.x create_agent 기반)
"""
import json
import logging
from datetime import datetime
from typing import AsyncGenerator
from langchain.agents import create_agent
from langchain_core.messages import HumanMessage, AIMessage, ToolMessage
from app.llm.models import get_coordinator_llm
from app.llm.prompts import COORDINATOR_SYSTEM_PROMPT
from app.llm.tools.graph_schema_tool import graph_schema_tool
from app.llm.tools.graph_cypher_tool import graph_cypher_qa_tool, graph_query_tool
from app.llm.tools.utility_tools import table_summary_tool, chart_recommendation_tool
from app.schemas.chat import ChatResponse, ChatAction, ToolResult, StepInfo

logger = logging.getLogger(__name__)

AVAILABLE_TOOLS = [
    graph_schema_tool,
    graph_cypher_qa_tool,
    graph_query_tool,
    table_summary_tool,
    chart_recommendation_tool,
]

TOOL_LABELS = {
    "graph_schema_tool":         "스키마 조회",
    "graph_cypher_qa_tool":      "Cypher 생성 및 실행",
    "graph_query_tool":          "Cypher 직접 실행",
    "table_summary_tool":        "데이터 요약",
    "chart_recommendation_tool": "차트 추천",
}


def _extract_content_parts(content: object) -> tuple[str, str]:
    """LangChain/OpenAI 호환 content 블록에서 (answer, thinking)을 추출한다."""
    if isinstance(content, str):
        return content, ""
    if isinstance(content, list):
        answer_chunks: list[str] = []
        thinking_chunks: list[str] = []
        for block in content:
            if isinstance(block, str):
                answer_chunks.append(block)
                continue
            if not isinstance(block, dict):
                continue
            block_type = block.get("type")
            if block_type in ("text", "output_text"):
                text = block.get("text")
                if isinstance(text, str):
                    answer_chunks.append(text)
            elif block_type in ("reasoning", "reasoning_content"):
                # thinking 모델의 추론 블록
                text = block.get("text")
                if isinstance(text, str):
                    thinking_chunks.append(text)

                summary = block.get("summary")
                if isinstance(summary, list):
                    for s in summary:
                        if isinstance(s, dict):
                            sum_text = s.get("text")
                            if isinstance(sum_text, str):
                                thinking_chunks.append(sum_text)
        return "".join(answer_chunks), "".join(thinking_chunks)
    return "", ""


def _extract_reasoning_from_message(msg: AIMessage) -> str:
    """AIMessage의 provider별 additional kwargs에서 reasoning 텍스트를 추출한다."""
    additional = getattr(msg, "additional_kwargs", {}) or {}
    candidates = [
        additional.get("reasoning_content"),
        additional.get("reasoning"),
        additional.get("thinking"),
    ]
    for item in candidates:
        if isinstance(item, str) and item.strip():
            return item
        if isinstance(item, list):
            texts = [x for x in item if isinstance(x, str)]
            if texts:
                return "".join(texts)
    return ""


def _build_agent():
    """coordinator agent 빌드"""
    llm = get_coordinator_llm()
    return create_agent(
        model=llm,
        tools=AVAILABLE_TOOLS,
        system_prompt=COORDINATOR_SYSTEM_PROMPT.format(
            current_date=datetime.now().strftime("%Y-%m-%d")
        ),
    )


def _build_messages(history: list[dict], context: dict, message: str):
    messages = []
    for msg in history[-6:]:
        if msg["role"] == "user":
            messages.append(HumanMessage(content=msg["content"]))
        else:
            messages.append(AIMessage(content=msg["content"]))

    context_prefix = ""
    if context.get("current_query"):
        context_prefix += f"[현재 실행 쿼리: {context['current_query']}]\n"
    if context.get("selected_node"):
        context_prefix += f"[선택된 노드: {context['selected_node']}]\n"

    messages.append(HumanMessage(content=f"{context_prefix}{message}" if context_prefix else message))
    return messages


def _extract_tool_result(tool_name: str, output_str: str) -> tuple[ToolResult | None, list[ChatAction], str]:
    """tool 출력 JSON에서 ToolResult, actions, 요약 문자열을 추출한다."""
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
    """
    coordinator를 실행하여 사용자 메시지에 대한 응답을 생성한다.
    """
    try:
        agent = _build_agent()
        messages = _build_messages(history, context, message)
        response = agent.invoke({"messages": messages})

        # 마지막 AIMessage에서 최종 답변 추출
        response_messages = response.get("messages", [])
        answer = ""
        thinking = ""
        for msg in reversed(response_messages):
            if isinstance(msg, AIMessage) and msg.content:
                extracted_answer, extracted_thinking = _extract_content_parts(msg.content)
                answer = extracted_answer or answer
                thinking = extracted_thinking or _extract_reasoning_from_message(msg) or thinking
                if answer:
                    break

        # 중간 단계 수집 (AIMessage tool_calls + ToolMessage 쌍)
        TOOL_LABELS = {
            "graph_schema_tool":        "스키마 조회",
            "graph_cypher_qa_tool":     "Cypher 생성 및 실행",
            "graph_query_tool":         "Cypher 직접 실행",
            "table_summary_tool":       "데이터 요약",
            "chart_recommendation_tool": "차트 추천",
        }
        # tool_call_id → input 매핑
        tool_inputs: dict[str, str] = {}
        for msg in response_messages:
            if isinstance(msg, AIMessage) and getattr(msg, "tool_calls", None):
                for tc in msg.tool_calls:
                    args = tc.get("args", {})
                    tool_inputs[tc["id"]] = next(iter(args.values()), "") if args else ""

        steps: list[StepInfo] = []
        for msg in response_messages:
            if not isinstance(msg, ToolMessage):
                continue
            tool_key = getattr(msg, "name", "")
            tool_call_id = getattr(msg, "tool_call_id", "")
            raw_input = tool_inputs.get(tool_call_id, "")

            # output 요약
            try:
                data = json.loads(msg.content)
                if "error" in data:
                    output_summary = f"오류: {data['error']}"
                elif data.get("cypher"):
                    row_count = data.get("row_count", "?")
                    output_summary = f"{row_count}건 반환\n```cypher\n{data['cypher']}\n```"
                elif isinstance(data, dict):
                    output_summary = str(data)[:2000]
                else:
                    output_summary = msg.content[:2000]
            except Exception:
                output_summary = msg.content[:2000]

            steps.append(StepInfo(
                tool=TOOL_LABELS.get(tool_key, tool_key),
                tool_key=tool_key,
                input=str(raw_input)[:2000],
                output=output_summary,
            ))

        # ToolMessage에서 tool 결과 추출
        tool_result = ToolResult()
        actions: list[ChatAction] = []

        for msg in response_messages:
            if not isinstance(msg, ToolMessage):
                continue
            # ToolMessage의 name으로 tool 종류 파악
            tool_name = getattr(msg, "name", "")
            if tool_name not in ("graph_cypher_qa_tool", "graph_query_tool"):
                continue
            try:
                data = json.loads(msg.content)
                if "error" in data:
                    continue

                tool_result.cypher = data.get("cypher", "")
                tool_result.graph = {
                    "nodes": data.get("nodes", []),
                    "edges": data.get("edges", []),
                    "raw": data.get("result", []),
                }
                tool_result.table = data.get("result", [])
                tool_result.summary = data.get("answer", "")

                if data.get("cypher"):
                    actions.append(ChatAction(type="apply_query", query=data["cypher"]))
                if data.get("nodes"):
                    actions.append(ChatAction(type="open_tab", tab="graph"))
                elif data.get("result"):
                    actions.append(ChatAction(type="open_tab", tab="table"))

            except (json.JSONDecodeError, TypeError):
                pass

        return ChatResponse(
            message=answer or "처리가 완료되었습니다.",
            actions=actions,
            tool_results=tool_result,
            steps=steps,
            thinking=thinking or None,
        )

    except Exception as e:
        logger.error(f"coordinator 실행 실패: {e}", exc_info=True)
        return ChatResponse(
            message=f"처리 중 오류가 발생했습니다: {str(e)}",
            actions=[],
            tool_results=ToolResult(),
        )


async def stream_coordinator(
    message: str,
    history: list[dict] = [],
    context: dict = {},
) -> AsyncGenerator[str, None]:
    """
    coordinator를 스트리밍으로 실행한다.
    SSE 형식의 JSON 문자열을 yield한다.
    이벤트 타입: step_start | step_end | token | done
    """
    agent = _build_agent()
    messages = _build_messages(history, context, message)

    steps: list[StepInfo] = []
    all_actions: list[ChatAction] = []
    final_tool_result = ToolResult()
    collected_thinking: list[str] = []
    step_inputs: dict[str, str] = {}   # run_id → input
    tools_running = 0

    try:
        async for event in agent.astream_events({"messages": messages}, version="v2"):
            kind = event["event"]
            name = event.get("name", "")
            run_id = event.get("run_id", "")

            if kind == "on_tool_start" and name in TOOL_LABELS:
                tools_running += 1
                input_data = event["data"].get("input", {})
                if isinstance(input_data, dict) and input_data:
                    input_str = str(next(iter(input_data.values()), ""))[:2000]
                else:
                    input_str = str(input_data)[:2000]
                step_inputs[run_id] = input_str
                yield json.dumps({
                    "type": "step_start",
                    "tool": TOOL_LABELS[name],
                    "tool_key": name,
                    "input": input_str,
                }, ensure_ascii=False)

            elif kind == "on_tool_end" and name in TOOL_LABELS:
                tools_running = max(0, tools_running - 1)
                output = event["data"].get("output", "")
                # astream_events v2에서 output은 ToolMessage 객체로 래핑될 수 있음
                if hasattr(output, "content"):
                    output_str = output.content if isinstance(output.content, str) else json.dumps(output.content)
                elif isinstance(output, dict):
                    output_str = json.dumps(output)
                else:
                    output_str = str(output)

                tool_result, actions, summary = _extract_tool_result(name, output_str)
                if tool_result:
                    final_tool_result = tool_result
                    all_actions.extend(actions)

                step = StepInfo(
                    tool=TOOL_LABELS[name],
                    tool_key=name,
                    input=step_inputs.pop(run_id, ""),
                    output=summary,
                )
                steps.append(step)
                yield json.dumps({
                    "type": "step_end",
                    "tool_key": name,
                    "output": summary,
                }, ensure_ascii=False)

            elif kind == "on_chat_model_stream" and tools_running == 0:
                chunk = event["data"].get("chunk")
                if chunk:
                    content, thinking = _extract_content_parts(getattr(chunk, "content", ""))
                    tool_call_chunks = getattr(chunk, "tool_call_chunks", [])
                    if thinking:
                        collected_thinking.append(thinking)
                        yield json.dumps({"type": "thinking_token", "content": thinking}, ensure_ascii=False)
                    if content and not tool_call_chunks:
                        yield json.dumps({"type": "token", "content": content}, ensure_ascii=False)

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
