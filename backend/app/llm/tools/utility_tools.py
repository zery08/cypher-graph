"""
테이블 요약 및 차트 추천 tool
"""
import json
import logging
from langchain.tools import tool

logger = logging.getLogger(__name__)


@tool
def table_summary_tool(data_json: str) -> str:
    """
    표 형식의 데이터를 요약합니다.
    행 수, 컬럼 목록, 주요 통계를 제공합니다.

    Args:
        data_json: JSON 배열 형식의 표 데이터

    Returns:
        데이터 요약 문자열
    """
    try:
        data = json.loads(data_json)
        if not data:
            return "데이터가 없습니다."

        rows = data if isinstance(data, list) else [data]
        columns = list(rows[0].keys()) if rows else []
        row_count = len(rows)

        # 수치형 컬럼 기본 통계
        numeric_stats = {}
        for col in columns:
            values = [r[col] for r in rows if isinstance(r.get(col), (int, float))]
            if values:
                numeric_stats[col] = {
                    "min": min(values),
                    "max": max(values),
                    "avg": sum(values) / len(values),
                    "count": len(values),
                }

        summary = {
            "row_count": row_count,
            "columns": columns,
            "numeric_stats": numeric_stats,
        }

        return json.dumps(summary, ensure_ascii=False)
    except Exception as e:
        logger.error(f"table_summary_tool 실패: {e}")
        return f"데이터 요약 실패: {str(e)}"


@tool
def chart_recommendation_tool(data_description: str) -> str:
    """
    데이터 특성을 분석하여 적합한 차트 유형을 추천합니다.

    Args:
        data_description: 데이터 구조와 분석 목적 설명

    Returns:
        추천 차트 유형과 설정 JSON
    """
    description_lower = data_description.lower()

    # 시계열/추이 데이터
    if any(kw in description_lower for kw in ["시간", "추이", "trend", "time", "step"]):
        return json.dumps(
            {
                "chart_type": "line",
                "reason": "시간 또는 step별 추이 분석에 적합",
                "config": {"xAxis": "time_or_step", "yAxis": "measurement_value"},
            },
            ensure_ascii=False,
        )

    # 분포 데이터
    if any(kw in description_lower for kw in ["분포", "distribution", "histogram"]):
        return json.dumps(
            {
                "chart_type": "histogram",
                "reason": "파라미터 분포 분석에 적합",
                "config": {"bins": 20},
            },
            ensure_ascii=False,
        )

    # wafer 간 비교
    if any(kw in description_lower for kw in ["비교", "compare", "wafer", "lot"]):
        return json.dumps(
            {
                "chart_type": "scatter",
                "reason": "wafer 또는 lot 간 파라미터 비교에 적합",
                "config": {"xAxis": "wafer_id", "yAxis": "parameter_value"},
            },
            ensure_ascii=False,
        )

    # 기본: 산점도
    return json.dumps(
        {
            "chart_type": "scatter",
            "reason": "일반적인 데이터 관계 시각화",
            "config": {},
        },
        ensure_ascii=False,
    )
