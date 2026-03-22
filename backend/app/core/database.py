"""
PostgreSQL 비동기 데이터베이스 연결 관리
SQLAlchemy async engine 및 세션 팩토리를 제공한다.
"""
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy.orm import DeclarativeBase
from app.core.config import settings

engine = create_async_engine(settings.database_url, echo=False, pool_pre_ping=True)
AsyncSessionLocal = async_sessionmaker(engine, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


async def get_db() -> AsyncSession | None:
    """FastAPI Depends용 DB 세션 제공자. DB 연결 불가 시 None을 반환한다."""
    try:
        async with AsyncSessionLocal() as session:
            yield session
    except Exception:
        yield None


async def init_db() -> None:
    """앱 시작 시 테이블 자동 생성"""
    from app.models import user, conversation  # noqa: F401 - 모델 임포트로 메타데이터 등록
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
