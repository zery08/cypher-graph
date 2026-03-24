"""
Cypher 생성·실행 tool
GraphCypherQAChain.from_llm 을 사용하여 자연어 → Cypher → 결과를 처리한다.
"""
import json
import logging
from langchain_neo4j import GraphCypherQAChain
from langchain_core.prompts import PromptTemplate
from app.llm.models import get_cypher_llm, get_answer_llm
from app.services.neo4j_service import get_graph, execute_query, parse_graph_result
from app.services.query_guard import sanitize_cypher_from_llm, QueryGuardError
from app.core.config import settings
from app.llm.prompts import CYPHER_GENERATION_PROMPT

logger = logging.getLogger(__name__)

TOOL_LABEL = "Cypher 생성 및 실행"

TOOL_SPEC = {
    "type": "function",
    "function": {
        "name": "graph_cypher_qa_tool",
        "description": (
            "자연어 질문을 받아 Neo4j Cypher 쿼리를 생성하고 실행하여 결과를 반환합니다. "
            "wafer, recipe, metrology 데이터에 대한 분석 질문에 사용하세요."
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


def run(args: dict) -> str:
    question: str = args.get("question", "")
    try:
        chain = _get_chain()
        response = chain.invoke({"query": question})

        # 중간 단계에서 생성된 Cypher 및 raw 결과 추출
        cypher = ""
        raw_result = []
        for step in response.get("intermediate_steps", []):
            if "query" in step:
                cypher = step["query"]
            if "context" in step:
                raw_result = step["context"]

        # query_guard 2차 검증 및 정리
        if cypher:
            try:
                cypher = sanitize_cypher_from_llm(cypher)
                logger.info(f"Cypher 검증 통과: {cypher}")
            except QueryGuardError as e:
                logger.warning(f"LLM 생성 Cypher 안전성 경고: {e}")

        # 검증된 Cypher 로 다시 실행해 정확한 노드/엣지를 파싱
        if cypher:
            try:
                raw_result, elapsed_ms = execute_query(cypher)
            except Exception as e:
                logger.warning(f"Cypher 재실행 실패, chain 결과 사용: {e}")
                elapsed_ms = 0
        else:
            elapsed_ms = 0

        graph_result = parse_graph_result(raw_result)

        return json.dumps(
            {
                "cypher": cypher,
                "nodes": [n.model_dump() for n in graph_result.nodes],
                "edges": [e.model_dump() for e in graph_result.edges],
                "result": raw_result[: settings.max_query_results],
                "answer": response.get("result", ""),
                "row_count": len(raw_result),
                "execution_time_ms": elapsed_ms,
            },
            ensure_ascii=False,
        )
    except Exception as e:
        logger.error(f"graph_cypher_qa_tool 실행 실패: {e}")
        return json.dumps({"error": str(e), "cypher": "", "result": []})
