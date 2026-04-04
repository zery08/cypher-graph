"""
Neo4j graph schema inspection tool.
"""
import json
import logging
import time

from app.services.neo4j_service import get_schema_info

logger = logging.getLogger(__name__)

TOOL_LABEL = "그래프 스키마 조회"

TOOL_SPEC = {
    "type": "function",
    "function": {
        "name": "graph_schema_tool",
        "description": (
            "Neo4j 그래프의 노드 라벨, 관계 타입, 프로퍼티를 조회합니다. "
            "질문이 모호하거나 첫 쿼리가 실패했을 때 먼저 사용하세요."
        ),
        "parameters": {
            "type": "object",
            "properties": {},
        },
    },
}


def _make_summary(schema: dict) -> str:
    labels = schema.get("node_labels", [])
    rels = schema.get("relationship_types", [])
    return (
        f"라벨 {len(labels)}개, 관계 {len(rels)}개 확인"
        + (f" | labels={', '.join(labels[:6])}" if labels else "")
        + (f" | rels={', '.join(rels[:6])}" if rels else "")
    )


def run(args: dict) -> str:
    started_at = time.monotonic()
    logger.info(f"[graph_schema_tool] 시작 args={args}")
    try:
        schema = get_schema_info()
        payload = {
            "node_labels": schema.get("node_labels", []),
            "relationship_types": schema.get("relationship_types", []),
            "properties": schema.get("properties", {}),
            "raw_schema": schema.get("raw_schema", ""),
            "summary": _make_summary(schema),
        }
        elapsed_ms = (time.monotonic() - started_at) * 1000
        logger.info(
            f"[graph_schema_tool] 완료 elapsed_ms={elapsed_ms:.1f} "
            f"labels={len(payload['node_labels'])} rels={len(payload['relationship_types'])}"
        )
        return json.dumps(payload, ensure_ascii=False)
    except Exception as e:
        logger.error(f"[graph_schema_tool] 실패: {e}", exc_info=True)
        return json.dumps({"error": str(e), "summary": "스키마 조회 실패"}, ensure_ascii=False)
