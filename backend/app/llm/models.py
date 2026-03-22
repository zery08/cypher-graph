"""
LLM 객체 생성 관리 모듈
coordinator, cypher, answer LLM을 환경변수 기반으로 제공한다.
"""
import logging
from langchain_openai import ChatOpenAI
from app.core.config import settings

logger = logging.getLogger(__name__)


def _make_llm(model: str, temperature: float = 0.0, max_tokens: int = 2048) -> ChatOpenAI:
    """OpenAI 호환 ChatOpenAI 인스턴스 생성"""
    return ChatOpenAI(
        model=model,
        temperature=temperature,
        max_tokens=max_tokens,
        openai_api_key=settings.openai_api_key,
        openai_api_base=settings.openai_base_url,
    )


def get_coordinator_llm() -> ChatOpenAI:
    """coordinator LLM 반환 - tool 선택 및 최종 답변 생성용"""
    logger.debug(f"coordinator LLM 생성: {settings.coordinator_model}")
    return _make_llm(settings.coordinator_model, temperature=0.1)


def get_cypher_llm() -> ChatOpenAI:
    """cypher LLM 반환 - 자연어 → Cypher 변환 전용"""
    logger.debug(f"cypher LLM 생성: {settings.cypher_model}")
    return _make_llm(settings.cypher_model, temperature=0.0)


def get_answer_llm() -> ChatOpenAI:
    """answer LLM 반환 - 결과 정리 및 사용자 친화적 설명 생성용"""
    logger.debug(f"answer LLM 생성: {settings.answer_model}")
    return _make_llm(settings.answer_model, temperature=0.2)
