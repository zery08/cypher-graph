"""
WaferFlow 백엔드 FastAPI 앱
반도체 공정/계측 데이터 탐색용 분석 워크스페이스 API
"""
import logging
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.sessions import SessionMiddleware
from app.core.config import settings
from app.core.database import init_db
from app.api.routes import health, chat, graph, auth, conversations

# 로깅 설정
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

app = FastAPI(
    title="WaferFlow API",
    description="반도체 공정/계측 데이터 탐색 및 LLM 분석 API",
    version="1.0.0",
)

# 세션 미들웨어 (Keycloak BFF용 HttpOnly 쿠키 세션)
app.add_middleware(SessionMiddleware, secret_key=settings.session_secret)

# CORS 설정
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 라우터 등록
app.include_router(health.router, prefix="/api", tags=["헬스체크"])
app.include_router(auth.router, prefix="/api", tags=["인증"])
app.include_router(chat.router, prefix="/api", tags=["채팅"])
app.include_router(graph.router, prefix="/api", tags=["그래프"])
app.include_router(conversations.router, prefix="/api", tags=["대화기록"])


@app.on_event("startup")
async def startup_event():
    logger.info("WaferFlow 백엔드 시작")
    logger.info(f"coordinator 모델: {settings.coordinator_model}")
    logger.info(f"cypher 모델: {settings.cypher_model}")
    logger.info(f"Neo4j URI: {settings.neo4j_uri}")
    try:
        await init_db()
        logger.info("PostgreSQL 테이블 초기화 완료")
    except Exception as e:
        logger.warning(f"PostgreSQL 연결 실패 — 대화 기록 기능 비활성화: {e}")


@app.on_event("shutdown")
async def shutdown_event():
    logger.info("WaferFlow 백엔드 종료")
