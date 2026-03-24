"""
LLM 객체 생성 관리 모듈
coordinator, cypher, answer LLM을 각각 독립적인 환경변수 기반으로 제공한다.
"""
import logging
from langchain_openai import ChatOpenAI
from app.core.config import settings

logger = logging.getLogger(__name__)


def get_coordinator_llm() -> ChatOpenAI:
    """coordinator LLM 반환 - tool 선택 및 최종 답변 생성용"""
    logger.debug(f"coordinator LLM 생성: {settings.coordinator_model}")
    return ChatOpenAI(
        model=settings.coordinator_model,
        temperature=0.1,
        max_tokens=2048,
        openai_api_key=settings.coordinator_api_key,
        openai_api_base=settings.coordinator_base_url,
    )


def get_cypher_llm() -> ChatOpenAI:
    """cypher LLM 반환 - 자연어 → Cypher 변환 전용"""
    logger.debug(f"cypher LLM 생성: {settings.cypher_model}")
    return ChatOpenAI(
        model=settings.cypher_model,
        temperature=0.0,
        max_tokens=2048,
        openai_api_key=settings.cypher_api_key,
        openai_api_base=settings.cypher_base_url,
    )


def get_answer_llm() -> ChatOpenAI:
    """answer LLM 반환 - 결과 정리 및 사용자 친화적 설명 생성용"""
    logger.debug(f"answer LLM 생성: {settings.answer_model}")
    return ChatOpenAI(
        model=settings.answer_model,
        temperature=0.2,
        max_tokens=2048,
        openai_api_key=settings.answer_api_key,
        openai_api_base=settings.answer_base_url,
    )
