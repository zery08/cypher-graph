"""
그래프 쿼리 및 스키마 엔드포인트
"""
import logging
from fastapi import APIRouter, HTTPException
from app.schemas.graph import QueryRequest, QueryResponse, SchemaResponse
from app.services.neo4j_service import execute_query, parse_graph_result, get_schema_info
from app.services.query_guard import validate_query, QueryGuardError

logger = logging.getLogger(__name__)
router = APIRouter()


@router.post("/graph/query", response_model=QueryResponse)
async def run_graph_query(request: QueryRequest):
    """
    사용자가 직접 입력한 Cypher를 실행한다.
    읽기 전용 검증 후 결과를 반환한다.
    """
    try:
        safe_cypher = validate_query(request.query)
    except QueryGuardError as e:
        raise HTTPException(status_code=400, detail=str(e))

    try:
        raw_results, elapsed_ms = execute_query(safe_cypher, request.parameters)
        graph_result = parse_graph_result(raw_results)

        return QueryResponse(
            result=graph_result,
            cypher=safe_cypher,
            row_count=len(raw_results),
            execution_time_ms=elapsed_ms,
        )
    except Exception as e:
        logger.error(f"쿼리 실행 실패: {e}")
        raise HTTPException(status_code=500, detail=f"쿼리 실행 실패: {str(e)}")


@router.get("/graph/schema", response_model=SchemaResponse)
async def get_graph_schema():
    """Neo4j 스키마 정보를 반환한다."""
    try:
        schema = get_schema_info()
        return SchemaResponse(**schema)
    except Exception as e:
        logger.error(f"스키마 조회 실패: {e}")
        raise HTTPException(status_code=500, detail=f"스키마 조회 실패: {str(e)}")
