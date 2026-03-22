"""
헬스 체크 엔드포인트
"""
from fastapi import APIRouter
from app.schemas.common import HealthResponse
from app.services.neo4j_service import check_connection

router = APIRouter()


@router.get("/health", response_model=HealthResponse)
async def health_check():
    """서비스 상태 및 Neo4j 연결 상태를 반환한다."""
    neo4j_ok = check_connection()
    return HealthResponse(
        status="ok" if neo4j_ok else "degraded",
        neo4j_connected=neo4j_ok,
    )
