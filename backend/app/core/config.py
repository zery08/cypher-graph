"""
애플리케이션 설정 관리 모듈
환경변수 기반으로 설정을 로드한다.
"""
from pydantic_settings import BaseSettings
from pydantic import Field


class Settings(BaseSettings):
    # Neo4j 연결 설정
    neo4j_uri: str = Field(default="bolt://localhost:7687", alias="NEO4J_URI")
    neo4j_username: str = Field(default="neo4j", alias="NEO4J_USERNAME")
    neo4j_password: str = Field(default="password", alias="NEO4J_PASSWORD")

    # LLM 모델 설정
    coordinator_model: str | None = Field(default=None, alias="COORDINATOR_MODEL")
    cypher_model: str | None = Field(default=None, alias="CYPHER_MODEL")
    answer_model: str | None = Field(default=None, alias="ANSWER_MODEL")

    # 역할별 OpenAI 호환 API 설정 (OpenRouter 등)
    coordinator_api_key: str | None = Field(default=None, alias="COORDINATOR_API_KEY")
    coordinator_base_url: str | None = Field(default=None, alias="COORDINATOR_BASE_URL")
    cypher_api_key: str | None = Field(default=None, alias="CYPHER_API_KEY")
    cypher_base_url: str | None = Field(default=None, alias="CYPHER_BASE_URL")
    answer_api_key: str | None = Field(default=None, alias="ANSWER_API_KEY")
    answer_base_url: str | None = Field(default=None, alias="ANSWER_BASE_URL")

    # 쿼리 제한 설정
    max_query_results: int = Field(default=100, alias="MAX_QUERY_RESULTS")

    # CORS 설정
    cors_origins: list[str] = Field(
        default=["http://localhost:5173", "http://localhost:3000"],
        alias="CORS_ORIGINS",
    )

    # Keycloak OIDC 설정
    keycloak_url: str = Field(default="http://localhost:8080", alias="KEYCLOAK_URL")
    keycloak_realm: str = Field(default="rcp", alias="KEYCLOAK_REALM")
    keycloak_client_id: str = Field(default="rcp-cypher", alias="KEYCLOAK_CLIENT_ID")
    keycloak_client_secret: str = Field(default="", alias="KEYCLOAK_CLIENT_SECRET")
    keycloak_redirect_uri: str = Field(
        default="http://localhost:8000/api/auth/callback",
        alias="KEYCLOAK_REDIRECT_URI",
    )

    # 세션 설정
    session_secret: str = Field(default="change-me-in-production", alias="SESSION_SECRET")

    # 프론트엔드 URL (로그인 후 리디렉트)
    frontend_url: str = Field(default="http://localhost:5173", alias="FRONTEND_URL")

    # PostgreSQL 설정
    database_url: str = Field(
        default="postgresql+asyncpg://postgres:password@localhost:5432/rcp_cypher",
        alias="DATABASE_URL",
    )

    model_config = {"env_file": ".env", "populate_by_name": True}


settings = Settings()
