"""
차트 유형 추천 tool
"""
import json
import logging
import time

logger = logging.getLogger(__name__)

TOOL_LABEL = "차트 추천"

TOOL_SPEC = {
    "type": "function",
    "function": {
        "name": "chart_recommendation_tool",
        "description": (
            "데이터 특성과 분석 목적을 보고 적합한 차트 유형을 추천합니다. "
            "충분한 조회 결과나 요약이 확보된 뒤 사용하세요."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "data_description": {
                    "type": "string",
                    "description": "데이터 구조와 분석 목적 설명 (예: step별 overlay error 추이)",
                }
            },
            "required": ["data_description"],
        },
    },
}


def run(args: dict) -> str:
    started_at = time.monotonic()
    desc = args.get("data_description", "").lower()
    logger.info(
        f"[chart_recommendation_tool] 시작 desc_len={len(desc)} desc={desc[:300]}"
    )

    if any(kw in desc for kw in ["시간", "추이", "trend", "time", "step"]):
        result = {"chart_type": "line", "reason": "step/시간 추이 분석에 적합",
                  "config": {"xAxis": "time_or_step", "yAxis": "measurement_value"}}
    elif any(kw in desc for kw in ["분포", "distribution", "histogram"]):
        result = {"chart_type": "histogram", "reason": "파라미터 분포 분석에 적합",
                  "config": {"bins": 20}}
    elif any(kw in desc for kw in ["비교", "compare", "wafer", "lot"]):
        result = {"chart_type": "scatter", "reason": "wafer/lot 간 파라미터 비교에 적합",
                  "config": {"xAxis": "wafer_id", "yAxis": "parameter_value"}}
    else:
        result = {"chart_type": "scatter", "reason": "일반적인 데이터 관계 시각화",
                  "config": {}}

    elapsed_ms = (time.monotonic() - started_at) * 1000
    logger.info(
        f"[chart_recommendation_tool] 완료 elapsed_ms={elapsed_ms:.1f} "
        f"chart_type={result['chart_type']} reason={result['reason']}"
    )
    return json.dumps(result, ensure_ascii=False)
