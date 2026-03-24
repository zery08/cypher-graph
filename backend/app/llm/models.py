"""
LLM 객체 생성 관리 모듈
coordinator, cypher, answer LLM을 환경변수 기반으로 제공한다.
"""
import logging
from langchain_openai import ChatOpenAI
from app.core.config import settings

logger = logging.getLogger(__name__)
DEFAULT_MODEL = "minimax/minimax-m2.5:free"


def _normalize_optional(value: str | None) -> str | None:
    """빈 문자열은 None으로 정규화한다."""
    return value if value not in (None, "") else None


def _resolve_model(model: str | None, setting_name: str) -> str:
    """모델 설정이 비어있으면 명시적으로 에러를 발생시켜 원인을 빠르게 알린다."""
    if model not in (None, ""):
        return model
    raise ValueError(
        f"{setting_name}가 설정되지 않았습니다. "
        f"예: {setting_name}={DEFAULT_MODEL}"
    )


def _make_llm(
    model: str | None,
    setting_name: str,
    temperature: float = 0.0,
    max_tokens: int = 2048,
    api_key: str | None = None,
    base_url: str | None = None,
) -> ChatOpenAI:
    """OpenAI 호환 ChatOpenAI 인스턴스 생성"""
    resolved_model = _resolve_model(model, setting_name)
    resolved_api_key = _normalize_optional(api_key)
    resolved_base_url = _normalize_optional(base_url)
    return ChatOpenAI(
        model=resolved_model,
        temperature=temperature,
        max_tokens=max_tokens,
        openai_api_key=resolved_api_key,
        openai_api_base=resolved_base_url,
    )


def get_coordinator_llm() -> ChatOpenAI:
    """coordinator LLM 반환 - tool 선택 및 최종 답변 생성용"""
    logger.debug(
        "coordinator LLM 생성: model=%s base_url=%s",
        settings.coordinator_model,
        _normalize_optional(settings.coordinator_base_url),
    )
    return _make_llm(
        settings.coordinator_model,
        setting_name="COORDINATOR_MODEL",
        temperature=0.1,
        api_key=settings.coordinator_api_key,
        base_url=settings.coordinator_base_url,
    )


def get_cypher_llm() -> ChatOpenAI:
    """cypher LLM 반환 - 자연어 → Cypher 변환 전용"""
    logger.debug(
        "cypher LLM 생성: model=%s base_url=%s",
        settings.cypher_model,
        _normalize_optional(settings.cypher_base_url),
    )
    return _make_llm(
        settings.cypher_model,
        setting_name="CYPHER_MODEL",
        temperature=0.0,
        api_key=settings.cypher_api_key,
        base_url=settings.cypher_base_url,
    )


def get_answer_llm() -> ChatOpenAI:
    """answer LLM 반환 - 결과 정리 및 사용자 친화적 설명 생성용"""
    logger.debug(
        "answer LLM 생성: model=%s base_url=%s",
        settings.answer_model,
        _normalize_optional(settings.answer_base_url),
    )
    return _make_llm(
        settings.answer_model,
        setting_name="ANSWER_MODEL",
        temperature=0.2,
        api_key=settings.answer_api_key,
        base_url=settings.answer_base_url,
    )
