"""
테이블 요약 및 차트 추천 tool
단일 파일에 두 tool이 있으므로, auto-discovery를 위해 두 번째 tool은
별도 파일(chart_recommendation_tool.py)로 분리한다.
이 파일은 table_summary_tool 하나만 담당한다.
"""
import json
import logging

logger = logging.getLogger(__name__)

TOOL_LABEL = "데이터 요약"

TOOL_SPEC = {
    "type": "function",
    "function": {
        "name": "table_summary_tool",
        "description": (
            "표 형식의 데이터를 요약합니다. "
            "행 수, 컬럼 목록, 주요 수치 통계를 제공합니다."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "data_json": {
                    "type": "string",
                    "description": "JSON 배열 형식의 표 데이터 문자열",
                }
            },
            "required": ["data_json"],
        },
    },
}


def run(args: dict) -> str:
    data_json: str = args.get("data_json", "[]")
    try:
        data = json.loads(data_json)
        if not data:
            return "데이터가 없습니다."

        rows = data if isinstance(data, list) else [data]
        columns = list(rows[0].keys()) if rows else []

        numeric_stats: dict = {}
        for col in columns:
            values = [r[col] for r in rows if isinstance(r.get(col), (int, float))]
            if values:
                numeric_stats[col] = {
                    "min": min(values),
                    "max": max(values),
                    "avg": round(sum(values) / len(values), 4),
                    "count": len(values),
                }

        return json.dumps(
            {"row_count": len(rows), "columns": columns, "numeric_stats": numeric_stats},
            ensure_ascii=False,
        )
    except Exception as e:
        logger.error(f"table_summary_tool 실패: {e}")
        return f"데이터 요약 실패: {str(e)}"
