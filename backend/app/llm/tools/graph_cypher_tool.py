"""
GraphCypherQAChain 기반 자연어 → Cypher → 결과 → 답변 tool
"""
import logging
import json
from langchain_neo4j import GraphCypherQAChain
from langchain.tools import tool
from app.llm.models import get_cypher_llm, get_answer_llm
from app.services.neo4j_service import get_graph
from app.services.query_guard import sanitize_cypher_from_llm, QueryGuardError
from app.core.config import settings

logger = logging.getLogger(__name__)

_chain_instance: GraphCypherQAChain | None = None


def get_cypher_chain() -> GraphCypherQAChain:
    """GraphCypherQAChain 싱글톤 인스턴스 반환"""
    global _chain_instance
    if _chain_instance is None:
        logger.info("GraphCypherQAChain 초기화 중...")
        graph = get_graph()
        _chain_instance = GraphCypherQAChain.from_llm(
            cypher_llm=get_cypher_llm(),
            qa_llm=get_answer_llm(),
            graph=graph,
            verbose=True,
            allow_dangerous_requests=True,  # query_guard로 2차 검증함
            return_intermediate_steps=True,
        )
        logger.info("GraphCypherQAChain 초기화 완료")
    return _chain_instance


@tool
def graph_cypher_qa_tool(question: str) -> str:
    """
    자연어 질문을 받아 Neo4j Cypher 쿼리를 생성하고 실행하여 답변을 반환합니다.
    wafer, recipe, metrology 데이터에 대한 분석 질문에 사용하세요.

    Args:
        question: 분석하고자 하는 자연어 질문 (한글 또는 영어)

    Returns:
        JSON 형식의 결과: cypher, result, answer 포함
    """
    try:
        from app.services.neo4j_service import parse_graph_result

        chain = get_cypher_chain()
        response = chain.invoke({"query": question})

        # 중간 단계에서 생성된 Cypher 및 raw 결과 추출
        cypher = ""
        raw_result = []
        if "intermediate_steps" in response:
            steps = response["intermediate_steps"]
            for step in steps:
                if "query" in step:
                    cypher = step["query"]
                if "context" in step:
                    raw_result = step["context"]

        # query_guard로 생성된 Cypher 정리 및 2차 검증
        if cypher:
            try:
                cypher = sanitize_cypher_from_llm(cypher)
                logger.info(f"생성된 Cypher 검증 통과: {cypher}")
            except QueryGuardError as e:
                logger.warning(f"LLM 생성 Cypher 안전성 경고: {e}")

        # chain 내부에서 실행된 결과는 Neo4j 객체가 없으므로,
        # 검증된 Cypher를 우리 execute_query로 다시 실행해 정확한 노드/엣지를 파싱한다.
        from app.services.neo4j_service import execute_query
        if cypher:
            try:
                raw_result, _ = execute_query(cypher)
            except Exception as e:
                logger.warning(f"Cypher 재실행 실패, chain 결과 사용: {e}")

        graph_result = parse_graph_result(raw_result)

        return json.dumps(
            {
                "cypher": cypher,
                "nodes": [n.model_dump() for n in graph_result.nodes],
                "edges": [e.model_dump() for e in graph_result.edges],
                "result": raw_result[:settings.max_query_results],
                "answer": response.get("result", ""),
                "row_count": len(raw_result),
            },
            ensure_ascii=False,
        )
    except Exception as e:
        logger.error(f"graph_cypher_qa_tool 실행 실패: {e}")
        return json.dumps({"error": str(e), "cypher": "", "result": [], "answer": ""})


@tool
def graph_query_tool(cypher: str) -> str:
    """
    직접 작성한 Cypher 쿼리를 실행합니다.
    query_guard 검증을 통과한 읽기 전용 쿼리만 실행됩니다.

    Args:
        cypher: 실행할 Cypher 쿼리 문자열

    Returns:
        JSON 형식의 쿼리 결과
    """
    from app.services.neo4j_service import execute_query, parse_graph_result

    try:
        safe_cypher = sanitize_cypher_from_llm(cypher)
        results, elapsed_ms = execute_query(safe_cypher)
        graph_result = parse_graph_result(results)

        return json.dumps(
            {
                "cypher": safe_cypher,
                "nodes": [n.model_dump() for n in graph_result.nodes],
                "edges": [e.model_dump() for e in graph_result.edges],
                "raw": results,
                "row_count": len(results),
                "execution_time_ms": elapsed_ms,
            },
            ensure_ascii=False,
        )
    except QueryGuardError as e:
        return json.dumps({"error": f"쿼리 검증 실패: {str(e)}", "cypher": cypher})
    except Exception as e:
        logger.error(f"graph_query_tool 실행 실패: {e}")
        return json.dumps({"error": str(e), "cypher": cypher})
