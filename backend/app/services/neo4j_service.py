"""
Neo4j 연결 및 쿼리 실행 서비스
싱글톤 패턴으로 그래프 연결을 관리한다.
"""
import time
import logging
from datetime import date, datetime, time as datetime_time
from typing import Any
from neo4j import GraphDatabase, graph as neo4j_graph
from langchain_neo4j import Neo4jGraph
from app.core.config import settings
from app.schemas.graph import GraphResult, GraphNode, GraphEdge

logger = logging.getLogger(__name__)

_graph_instance: Neo4jGraph | None = None
_driver_instance = None


def get_driver():
    """neo4j 드라이버 싱글톤 반환 (직접 쿼리 실행용)"""
    global _driver_instance
    if _driver_instance is None:
        _driver_instance = GraphDatabase.driver(
            settings.neo4j_uri,
            auth=(settings.neo4j_username, settings.neo4j_password),
        )
    return _driver_instance


def get_graph() -> Neo4jGraph:
    """Neo4jGraph 싱글톤 반환 (LangChain schema 조회 / GraphCypherQAChain 용)"""
    global _graph_instance
    if _graph_instance is None:
        logger.info("Neo4jGraph 연결 초기화 중...")
        _graph_instance = Neo4jGraph(
            url=settings.neo4j_uri,
            username=settings.neo4j_username,
            password=settings.neo4j_password,
            refresh_schema=False,
        )
        logger.info("Neo4jGraph 연결 완료")
    return _graph_instance


def check_connection() -> bool:
    """Neo4j 연결 상태 확인"""
    try:
        driver = get_driver()
        driver.verify_connectivity()
        return True
    except Exception as e:
        logger.error(f"Neo4j 연결 실패: {e}")
        return False


def _serialize_value(value: Any) -> Any:
    """neo4j 값을 JSON 직렬화 가능한 형태로 변환"""
    # neo4j temporal types(neo4j.time.DateTime 등)와 python datetime은 문자열로 변환
    if isinstance(value, (datetime, date, datetime_time)):
        return value.isoformat()
    if hasattr(value, "iso_format") and callable(value.iso_format):
        try:
            return value.iso_format()
        except Exception:
            pass
    if hasattr(value, "to_native") and callable(value.to_native):
        try:
            native = value.to_native()
            if native is not value:
                return _serialize_value(native)
        except Exception:
            pass
    if isinstance(value, (neo4j_graph.Node, neo4j_graph.Relationship)):
        return {k: _serialize_value(v) for k, v in dict(value).items()}
    if isinstance(value, (list, tuple)):
        return [_serialize_value(v) for v in value]
    if isinstance(value, dict):
        return {k: _serialize_value(v) for k, v in value.items()}
    return value


def execute_query(cypher: str, params: dict[str, Any] = {}) -> tuple[list[dict], float]:
    """
    Cypher 쿼리를 neo4j 드라이버로 직접 실행한다.
    Node/Relationship 객체를 보존해 parse_graph_result에서 활용한다.
    """
    start = time.monotonic()
    driver = get_driver()

    raw_records: list[dict] = []
    node_edge_records: list[dict] = []  # 파싱용 원본 객체 보존

    with driver.session() as session:
        result = session.run(cypher, params)
        for record in result:
            # 파싱용: Node/Relationship 객체 그대로 보존
            node_edge_records.append(dict(record))
            # raw용: JSON 직렬화 가능하게 변환
            raw_records.append({k: _serialize_value(v) for k, v in record.items()})

    elapsed_ms = (time.monotonic() - start) * 1000
    logger.debug(f"쿼리 실행 완료 ({elapsed_ms:.1f}ms): {cypher[:80]}")

    # parse_graph_result를 위해 node_edge_records를 같이 반환
    _last_node_edge_records.clear()
    _last_node_edge_records.extend(node_edge_records)

    return raw_records, elapsed_ms


# 마지막 쿼리의 node/edge 레코드를 임시 보관 (parse_graph_result에서 사용)
_last_node_edge_records: list[dict] = []


def parse_graph_result(raw_results: list[dict]) -> GraphResult:
    """
    쿼리 결과에서 노드와 엣지를 추출하여 GraphResult로 변환한다.
    execute_query 직후 호출 시 Neo4j Node/Relationship 객체를 활용한다.
    """
    nodes: dict[str, GraphNode] = {}
    edges: list[GraphEdge] = []
    seen_edge_ids: set[str] = set()

    # execute_query가 저장해둔 원본 객체 레코드 사용
    records_to_parse = _last_node_edge_records if _last_node_edge_records else raw_results

    for record in records_to_parse:
        for value in record.values():
            if isinstance(value, neo4j_graph.Node):
                node_id = value.element_id
                if node_id not in nodes:
                    nodes[node_id] = GraphNode(
                        id=node_id,
                        labels=list(value.labels),
                        properties=dict(value),
                    )
            elif isinstance(value, neo4j_graph.Relationship):
                edge_id = value.element_id
                if edge_id not in seen_edge_ids:
                    seen_edge_ids.add(edge_id)
                    edges.append(
                        GraphEdge(
                            id=edge_id,
                            type=value.type,
                            source=value.start_node.element_id,
                            target=value.end_node.element_id,
                            properties=dict(value),
                        )
                    )

    return GraphResult(
        nodes=list(nodes.values()),
        edges=edges,
        raw=raw_results,
    )


def get_schema_info() -> dict[str, Any]:
    """Neo4j 스키마 정보 조회"""
    graph = get_graph()
    try:
        graph.refresh_schema()
    except Exception as e:
        logger.warning(f"스키마 갱신 실패: {e}")

    structured = graph.get_structured_schema
    return {
        "node_labels": list(structured.get("node_props", {}).keys()),
        "relationship_types": [
            r["type"] for r in structured.get("relationships", [])
        ],
        "properties": {
            label: [p["property"] for p in props]
            for label, props in structured.get("node_props", {}).items()
        },
        "raw_schema": graph.schema,
    }
