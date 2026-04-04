"""
Cypher 생성·실행 tool
GraphCypherQAChain.from_llm 을 사용하여 자연어 → Cypher → 결과를 처리한다.
"""
import json
import logging
import time
import uuid
from typing import Any

from langchain_neo4j import GraphCypherQAChain
from langchain_core.prompts import PromptTemplate
from app.llm.models import get_cypher_llm, get_answer_llm
from app.services.neo4j_service import get_graph, execute_query, parse_graph_result
from app.services.query_guard import sanitize_cypher_from_llm, QueryGuardError
from app.core.config import settings
from app.llm.prompts import CYPHER_GENERATION_PROMPT, ANSWER_FORMATTING_PROMPT

logger = logging.getLogger(__name__)

TOOL_LABEL = "Cypher 생성 및 실행"

TOOL_SPEC = {
    "type": "function",
    "function": {
        "name": "graph_cypher_qa_tool",
        "description": (
            "간단한 자연어 질문을 받아 Neo4j Cypher 쿼리를 생성하고 실행한 뒤 답변까지 반환합니다. "
            "빠른 end-to-end 조회에 우선 사용하고, 결과가 비거나 구조가 모호하면 "
            "graph_schema_tool 또는 graph_query_tool로 더 정밀하게 진행하세요."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "question": {
                    "type": "string",
                    "description": "분석하고자 하는 자연어 질문 (한글 또는 영어)",
                }
            },
            "required": ["question"],
        },
    },
}

_chain_instance: GraphCypherQAChain | None = None

# LLM 컨텍스트에 넣지 않을 전체 결과를 임시 보관하는 side store
# coordinator가 ToolMessage를 처리할 때 result_id로 꺼내 쓴다.
_result_store: dict[str, dict] = {}


def get_full_result(result_id: str) -> dict | None:
    """result_id로 전체 페이로드를 꺼내고 store에서 제거한다."""
    return _result_store.pop(result_id, None)


def _preview_text(value: Any, limit: int = 300) -> str:
    if not isinstance(value, str):
        try:
            value = json.dumps(value, ensure_ascii=False)
        except Exception:
            value = repr(value)
    value = value.replace("\n", "\\n")
    return value if len(value) <= limit else f"{value[:limit]}..."


def _get_chain() -> GraphCypherQAChain:
    """GraphCypherQAChain 싱글톤 반환"""
    global _chain_instance
    if _chain_instance is None:
        logger.info("GraphCypherQAChain 초기화 중...")
        cypher_prompt = PromptTemplate.from_template(CYPHER_GENERATION_PROMPT).partial(
            max_results=settings.max_query_results
        )
        _chain_instance = GraphCypherQAChain.from_llm(
            cypher_llm=get_cypher_llm(),
            qa_llm=get_answer_llm(),
            graph=get_graph(),
            cypher_prompt=cypher_prompt,
            top_k=settings.max_query_results,
            verbose=True,
            allow_dangerous_requests=True,   # query_guard 로 2차 검증함
            return_intermediate_steps=True,
        )
        logger.info("GraphCypherQAChain 초기화 완료")
    return _chain_instance


def _message_text(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for block in content:
            if isinstance(block, dict):
                parts.append(block.get("text", "") or block.get("content", ""))
            else:
                parts.append(str(block))
        return "".join(parts)
    return "" if content is None else str(content)


def _extract_chain_outputs(response: dict) -> tuple[str, list[dict], str]:
    cypher = ""
    raw_result: list[dict] = []
    intermediate_steps = response.get("intermediate_steps", [])
    logger.info(f"[graph_cypher_qa_tool] intermediate_steps={len(intermediate_steps)}")
    for idx, step in enumerate(intermediate_steps):
        if "query" in step:
            cypher = step["query"]
            logger.info(
                f"[graph_cypher_qa_tool] intermediate[{idx}] query={_preview_text(cypher, 800)}"
            )
        if "context" in step:
            raw_result = step["context"]
            logger.info(
                f"[graph_cypher_qa_tool] intermediate[{idx}] context_rows={len(raw_result)}"
            )
    return cypher, raw_result, response.get("result", "")


def _get_schema_text() -> str:
    graph = get_graph()
    return getattr(graph, "schema", "") or ""


def _generate_cypher_fallback(question: str) -> str:
    logger.info("[graph_cypher_qa_tool] fallback Cypher 생성 시작")
    prompt = PromptTemplate.from_template(CYPHER_GENERATION_PROMPT).partial(
        max_results=settings.max_query_results
    )
    rendered = prompt.format(schema=_get_schema_text(), question=question)
    response = get_cypher_llm().invoke(rendered)
    cypher = _message_text(response.content).strip()
    logger.info(
        f"[graph_cypher_qa_tool] fallback Cypher 생성 완료 cypher={_preview_text(cypher, 800)}"
    )
    return cypher


def _generate_answer_fallback(cypher: str, raw_result: list[dict]) -> str:
    logger.info(
        f"[graph_cypher_qa_tool] fallback answer 생성 시작 rows={len(raw_result)}"
    )
    prompt = PromptTemplate.from_template(ANSWER_FORMATTING_PROMPT)
    rendered = prompt.format(
        cypher=cypher or "(cypher unavailable)",
        result=json.dumps(raw_result[: settings.max_query_results], ensure_ascii=False),
    )
    response = get_answer_llm().invoke(rendered)
    answer = _message_text(response.content).strip()
    logger.info(
        f"[graph_cypher_qa_tool] fallback answer 생성 완료 answer={_preview_text(answer, 500)}"
    )
    return answer


def _followup_hint(
    *,
    chain_error: str | None,
    query_guard_error: str | None,
    execution_error: str | None,
    cypher: str,
) -> str | None:
    if chain_error:
        return (
            "graph_cypher_qa_tool이 직접 응답을 만들지 못했습니다. "
            "graph_schema_tool로 구조를 확인한 뒤 graph_query_tool로 명시적 Cypher를 실행하세요."
        )
    if query_guard_error:
        return (
            "생성된 Cypher가 안전성 검증을 통과하지 못했습니다. "
            "graph_schema_tool로 프로퍼티를 확인하고 더 보수적인 읽기 전용 Cypher를 사용하세요."
        )
    if execution_error:
        return (
            "실행 단계에서 오류가 발생했습니다. "
            "graph_schema_tool로 스키마를 다시 확인하고 graph_query_tool로 더 단순한 Cypher를 시도하세요."
        )
    if not cypher:
        return (
            "유효한 Cypher를 만들지 못했습니다. "
            "graph_schema_tool로 라벨과 관계를 먼저 확인하세요."
        )
    return None


def run(args: dict) -> str:
    question: str = args.get("question", "")
    started_at = time.monotonic()
    logger.info(
        f"[graph_cypher_qa_tool] 시작 question_len={len(question)} "
        f"question={_preview_text(question, 500)}"
    )
    notes: list[str] = []
    chain_error: str | None = None
    query_guard_error: str | None = None
    execution_error: str | None = None
    raw_result: list[dict] = []
    cypher = ""
    answer = ""
    response: dict = {}
    elapsed_ms = 0.0
    source = "graph_cypher_chain"
    used_fallback_cypher = False

    try:
        try:
            chain = _get_chain()
            chain_started_at = time.monotonic()
            logger.info("[graph_cypher_qa_tool] chain.invoke 시작")
            response = chain.invoke({"query": question})
            chain_elapsed_ms = (time.monotonic() - chain_started_at) * 1000
            logger.info(
                f"[graph_cypher_qa_tool] chain.invoke 완료 elapsed_ms={chain_elapsed_ms:.1f} "
                f"keys={list(response.keys())}"
            )
            cypher, raw_result, answer = _extract_chain_outputs(response)
        except Exception as e:
            chain_error = str(e)
            notes.append("GraphCypherQAChain 실행 실패")
            logger.error(f"[graph_cypher_qa_tool] chain.invoke 실패: {e}", exc_info=True)

        if cypher:
            logger.info(
                f"[graph_cypher_qa_tool] query_guard 시작 cypher={_preview_text(cypher, 800)}"
            )
            try:
                cypher = sanitize_cypher_from_llm(cypher)
                logger.info(
                    f"[graph_cypher_qa_tool] query_guard 통과 cypher={_preview_text(cypher, 800)}"
                )
            except QueryGuardError as e:
                query_guard_error = str(e)
                notes.append("chain이 생성한 Cypher가 query_guard를 통과하지 못함")
                logger.warning(f"[graph_cypher_qa_tool] LLM 생성 Cypher 안전성 경고: {e}")
                cypher = ""

        if not cypher and question:
            try:
                fallback_cypher = _generate_cypher_fallback(question)
                if fallback_cypher:
                    used_fallback_cypher = True
                    source = "fallback_cypher_llm"
                    logger.info(
                        f"[graph_cypher_qa_tool] fallback query_guard 시작 "
                        f"cypher={_preview_text(fallback_cypher, 800)}"
                    )
                    cypher = sanitize_cypher_from_llm(fallback_cypher)
                    logger.info(
                        f"[graph_cypher_qa_tool] fallback query_guard 통과 "
                        f"cypher={_preview_text(cypher, 800)}"
                    )
                    query_guard_error = None
                else:
                    notes.append("fallback Cypher 생성 결과가 비어 있음")
            except QueryGuardError as e:
                query_guard_error = str(e)
                notes.append("fallback Cypher도 query_guard를 통과하지 못함")
                logger.warning(f"[graph_cypher_qa_tool] fallback Cypher 안전성 경고: {e}")
                cypher = ""
            except Exception as e:
                notes.append("fallback Cypher 생성 실패")
                logger.warning(f"[graph_cypher_qa_tool] fallback Cypher 생성 실패: {e}", exc_info=True)

        if cypher:
            try:
                logger.info(
                    f"[graph_cypher_qa_tool] Cypher 재실행 시작 cypher={_preview_text(cypher, 800)}"
                )
                raw_result, elapsed_ms = execute_query(cypher)
                logger.info(
                    f"[graph_cypher_qa_tool] Cypher 재실행 완료 rows={len(raw_result)} "
                    f"elapsed_ms={elapsed_ms:.1f}"
                )
            except Exception as e:
                execution_error = str(e)
                notes.append("Cypher 재실행 실패")
                logger.warning(f"[graph_cypher_qa_tool] Cypher 재실행 실패, chain 결과 사용: {e}")
                elapsed_ms = 0
        else:
            logger.info("[graph_cypher_qa_tool] 유효한 Cypher 없음, chain context만 사용")

        logger.info(f"[graph_cypher_qa_tool] 그래프 파싱 시작 raw_rows={len(raw_result)}")
        graph_result = parse_graph_result(raw_result)

        if not raw_result:
            answer = "조회된 데이터가 없습니다."
        elif not answer:
            try:
                answer = _generate_answer_fallback(cypher, raw_result)
            except Exception as e:
                notes.append("fallback answer 생성 실패")
                logger.warning(f"[graph_cypher_qa_tool] fallback answer 생성 실패: {e}", exc_info=True)

        followup_hint = _followup_hint(
            chain_error=chain_error,
            query_guard_error=query_guard_error,
            execution_error=execution_error,
            cypher=cypher,
        )
        needs_followup = bool(followup_hint)

        logger.info(
            f"[graph_cypher_qa_tool] 그래프 파싱 완료 nodes={len(graph_result.nodes)} "
            f"edges={len(graph_result.edges)} answer_len={len(answer)} "
            f"used_fallback_cypher={used_fallback_cypher}"
        )

        # 전체 데이터를 side store에 보관 (LLM 컨텍스트에는 넣지 않음)
        result_id = uuid.uuid4().hex[:12]
        _result_store[result_id] = {
            "cypher": cypher,
            "nodes": [n.model_dump() for n in graph_result.nodes],
            "edges": [e.model_dump() for e in graph_result.edges],
            "result": raw_result[: settings.max_query_results],
            "answer": answer,
            "row_count": len(raw_result),
            "empty_result": len(raw_result) == 0,
            "needs_followup": needs_followup,
            "followup_hint": followup_hint,
        }

        # LLM이 볼 compact 요약만 반환 (answer + cypher + row_count + 미리보기 3건)
        compact = {
            "result_id": result_id,
            "answer": answer,
            "cypher": cypher,
            "row_count": len(raw_result),
            "preview": raw_result[:3],
            "empty_result": len(raw_result) == 0,
            "needs_followup": needs_followup,
            "followup_hint": followup_hint,
        }
        total_elapsed_ms = (time.monotonic() - started_at) * 1000
        logger.info(
            f"[graph_cypher_qa_tool] 완료 total_elapsed_ms={total_elapsed_ms:.1f} "
            f"row_count={len(raw_result)} result_id={result_id} "
            f"answer={_preview_text(answer, 300)}"
        )

        return json.dumps(compact, ensure_ascii=False)
    except Exception as e:
        logger.error(f"graph_cypher_qa_tool 실행 실패: {e}", exc_info=True)
        return json.dumps(
            {
                "error": str(e),
                "cypher": cypher,
                "result": raw_result,
                "notes": notes,
                "needs_followup": True,
            },
            ensure_ascii=False,
        )
