"""
Validated direct Cypher execution tool.
"""
import json
import logging
import time
from typing import Any

from app.core.config import settings
from app.services.neo4j_service import execute_query, parse_graph_result
from app.services.query_guard import sanitize_cypher_from_llm, QueryGuardError

logger = logging.getLogger(__name__)

TOOL_LABEL = "직접 Cypher 실행"

TOOL_SPEC = {
    "type": "function",
    "function": {
        "name": "graph_query_tool",
        "description": (
            "이미 작성된 읽기 전용 Cypher를 검증 후 실행합니다. "
            "스키마를 확인했거나 더 정밀한 제어가 필요할 때 사용하세요."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "cypher": {
                    "type": "string",
                    "description": "실행할 읽기 전용 Cypher 쿼리",
                }
            },
            "required": ["cypher"],
        },
    },
}


def _preview_text(value: Any, limit: int = 300) -> str:
    text = value if isinstance(value, str) else repr(value)
    text = text.replace("\n", "\\n")
    return text if len(text) <= limit else f"{text[:limit]}..."


def run(args: dict) -> str:
    raw_cypher = args.get("cypher", "")
    started_at = time.monotonic()
    logger.info(
        f"[graph_query_tool] 시작 cypher={_preview_text(raw_cypher, 800)}"
    )
    try:
        cypher = sanitize_cypher_from_llm(raw_cypher)
        logger.info(
            f"[graph_query_tool] query_guard 통과 cypher={_preview_text(cypher, 800)}"
        )
    except QueryGuardError as e:
        logger.warning(f"[graph_query_tool] query_guard 실패: {e}")
        return json.dumps(
            {
                "error": str(e),
                "cypher": raw_cypher,
                "result": [],
                "nodes": [],
                "edges": [],
                "row_count": 0,
                "execution_time_ms": 0,
            },
            ensure_ascii=False,
        )

    try:
        raw_result, elapsed_ms = execute_query(cypher)
        graph_result = parse_graph_result(raw_result)
        payload = {
            "cypher": cypher,
            "nodes": [n.model_dump() for n in graph_result.nodes],
            "edges": [e.model_dump() for e in graph_result.edges],
            "result": raw_result[: settings.max_query_results],
            "answer": "",
            "row_count": len(raw_result),
            "execution_time_ms": elapsed_ms,
        }
        total_elapsed_ms = (time.monotonic() - started_at) * 1000
        logger.info(
            f"[graph_query_tool] 완료 total_elapsed_ms={total_elapsed_ms:.1f} "
            f"row_count={payload['row_count']} nodes={len(payload['nodes'])} "
            f"edges={len(payload['edges'])}"
        )
        return json.dumps(payload, ensure_ascii=False)
    except Exception as e:
        logger.error(f"[graph_query_tool] 실패: {e}", exc_info=True)
        return json.dumps(
            {
                "error": str(e),
                "cypher": cypher,
                "result": [],
                "nodes": [],
                "edges": [],
                "row_count": 0,
                "execution_time_ms": 0,
            },
            ensure_ascii=False,
        )
