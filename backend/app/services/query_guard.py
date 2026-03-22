"""
Cypher 쿼리 안전성 검증 모듈
쓰기/삭제/관리성 쿼리를 차단하고 결과 행 수를 제한한다.
"""
import re
from app.core.config import settings

# 금지 키워드 목록
FORBIDDEN_KEYWORDS = [
    r"\bCREATE\b",
    r"\bMERGE\b",
    r"\bDELETE\b",
    r"\bDETACH\s+DELETE\b",
    r"\bSET\b",
    r"\bREMOVE\b",
    r"\bDROP\b",
    r"\bCALL\s+dbms\b",
    r"\bCALL\s+apoc\.periodic\b",
    r"\bCALL\s+apoc\.schema\b",
    r"\bLOAD\s+CSV\b",
    r"\bFOREACH\b",
]

# 주의 키워드 (경고는 하되 차단하지 않음)
WARNING_KEYWORDS = [
    r"\bEXPLAIN\b",
    r"\bPROFILE\b",
]


class QueryGuardError(Exception):
    """쿼리 안전성 검증 실패 예외"""
    pass


def validate_query(cypher: str) -> str:
    """
    Cypher 쿼리를 검증하고 정리된 쿼리를 반환한다.
    금지된 패턴이 있으면 QueryGuardError를 발생시킨다.
    LIMIT이 없으면 자동으로 추가한다.
    """
    upper = cypher.upper().strip()

    # 멀티 스테이트먼트 차단 (세미콜론으로 구분된 복수 쿼리)
    statements = [s.strip() for s in cypher.split(";") if s.strip()]
    if len(statements) > 1:
        raise QueryGuardError("복수 쿼리(멀티 스테이트먼트)는 허용되지 않습니다.")

    # 금지 키워드 검사
    for pattern in FORBIDDEN_KEYWORDS:
        if re.search(pattern, upper):
            keyword = re.search(pattern, upper).group()
            raise QueryGuardError(
                f"보안상 허용되지 않는 키워드가 포함되어 있습니다: {keyword}"
            )

    # LIMIT 강제 추가
    cleaned = cypher.strip().rstrip(";")
    if not re.search(r"\bLIMIT\s+\d+\b", upper):
        cleaned = f"{cleaned} LIMIT {settings.max_query_results}"

    return cleaned


def sanitize_cypher_from_llm(cypher: str) -> str:
    """
    LLM이 생성한 Cypher를 정리하고 검증한다.
    코드 블록 마크다운 제거 후 validate_query를 실행한다.
    """
    # ```cypher ... ``` 형식 제거
    cypher = re.sub(r"```(?:cypher)?\s*", "", cypher, flags=re.IGNORECASE)
    # 백틱 없이 'cypher' 키워드만으로 시작하는 경우 제거 (일부 LLM이 이렇게 반환)
    cypher = re.sub(r"^cypher\s*\n", "", cypher.strip(), flags=re.IGNORECASE)
    cypher = cypher.strip()

    return validate_query(cypher)
