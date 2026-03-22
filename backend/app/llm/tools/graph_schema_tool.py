"""
그래프 스키마 조회 tool
Cypher 생성 전 schema grounding 용도로 사용한다.
"""
import logging
from langchain.tools import tool
from app.services.neo4j_service import get_schema_info

logger = logging.getLogger(__name__)


@tool
def graph_schema_tool(query: str = "") -> str:
    """
    Neo4j 데이터베이스의 노드 레이블, 관계 타입, 속성 정보를 조회합니다.
    Cypher 쿼리 생성 전에 반드시 호출하여 스키마를 확인하세요.
    """
    try:
        schema = get_schema_info()
        lines = ["## Neo4j 스키마 정보\n"]

        lines.append("### 노드 레이블")
        for label in schema["node_labels"]:
            props = schema["properties"].get(label, [])
            lines.append(f"- {label}: {', '.join(props)}")

        lines.append("\n### 관계 타입")
        for rel_type in schema["relationship_types"]:
            lines.append(f"- {rel_type}")

        return "\n".join(lines)
    except Exception as e:
        logger.error(f"스키마 조회 실패: {e}")
        return f"스키마 조회 중 오류 발생: {str(e)}"
