"""
chart_build_tool - 실제 데이터를 받아 Recharts 차트 설정을 생성한다.

사용 시점:
  - graph_cypher_qa_tool / graph_query_tool로 데이터를 조회한 뒤
  - 사용자가 차트/시각화를 요청했을 때
  - data_json에는 조회된 row 배열 JSON 문자열을 전달한다.
"""
import json
import logging
import statistics
import time

logger = logging.getLogger(__name__)

TOOL_LABEL = "차트 생성"

TOOL_SPEC = {
    "type": "function",
    "function": {
        "name": "chart_build_tool",
        "description": (
            "조회된 데이터 배열을 받아 프론트엔드 Recharts 차트 설정을 생성합니다. "
            "graph_cypher_qa_tool 또는 graph_query_tool 결과의 'result' 필드를 "
            "data_json에 JSON 문자열로 전달하세요. "
            "차트 유형(line/bar/scatter)과 X·Y축을 자동으로 결정합니다."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "data_json": {
                    "type": "string",
                    "description": "JSON 배열 문자열 (조회된 row 목록)",
                },
                "intent": {
                    "type": "string",
                    "description": "시각화 의도 설명 (예: step별 overlay error 추이, wafer별 계측값 비교)",
                },
                "x_key": {
                    "type": "string",
                    "description": "X축 컬럼명. 생략하면 자동 선택.",
                },
                "y_keys": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Y축 컬럼명 목록. 생략하면 수치 컬럼 전체(최대 6개).",
                },
                "chart_type": {
                    "type": "string",
                    "enum": ["line", "bar", "scatter", "auto"],
                    "description": "차트 유형. auto이면 intent와 데이터 구조로 자동 결정.",
                },
            },
            "required": ["data_json", "intent"],
        },
    },
}

# X축 후보 힌트
_TIME_HINTS = ("step", "time", "date", "seq", "order", "idx", "index", "no", "num")
_ID_HINTS = ("id", "wafer", "lot", "chamber", "name", "label", "product", "type")


def _classify_columns(rows: list[dict]) -> tuple[list[str], list[str]]:
    """수치형 / 범주형 컬럼 분류"""
    numeric, categorical = [], []
    for col in rows[0].keys():
        vals = [r.get(col) for r in rows if r.get(col) is not None]
        if not vals:
            categorical.append(col)
            continue
        try:
            [float(v) for v in vals]
            numeric.append(col)
        except (TypeError, ValueError):
            categorical.append(col)
    return numeric, categorical


def _pick_x_key(
    numeric: list[str], categorical: list[str], intent: str
) -> tuple[str, str]:
    """(x_key, x_type) 반환. x_type은 'numeric' | 'categorical'"""
    intent_lower = intent.lower()

    # intent에 컬럼명이 직접 언급된 경우 우선
    for col in categorical + numeric:
        if col.lower() in intent_lower:
            return col, ("categorical" if col in categorical else "numeric")

    # 범주형 중 식별자 힌트
    for col in categorical:
        if any(h in col.lower() for h in _ID_HINTS):
            return col, "categorical"

    # 수치형 중 시간/순서 힌트
    for col in numeric:
        if any(h in col.lower() for h in _TIME_HINTS):
            return col, "numeric"

    if categorical:
        return categorical[0], "categorical"
    if numeric:
        return numeric[0], "numeric"
    return "_index", "numeric"


def _pick_chart_type(intent: str, x_type: str) -> str:
    il = intent.lower()
    if any(k in il for k in ["scatter", "산점도", "분포", "distribution", "outlier", "이상치"]):
        return "scatter"
    if any(k in il for k in ["bar", "막대", "비교", "compare", "count", "개수", "현황"]):
        return "bar"
    if any(k in il for k in ["line", "추이", "trend", "변화", "시계열", "흐름"]):
        return "line"
    return "bar" if x_type == "categorical" else "line"


def run(args: dict) -> str:
    started_at = time.monotonic()
    data_json: str = args.get("data_json", "[]")
    intent: str = args.get("intent", "")
    x_key_hint: str = args.get("x_key", "")
    y_keys_hint: list = args.get("y_keys") or []
    chart_type_hint: str = args.get("chart_type", "auto")

    logger.info(f"[chart_build_tool] 시작 intent={intent[:100]} data_len={len(data_json)}")

    try:
        rows = json.loads(data_json)
        if not isinstance(rows, list):
            rows = [rows]
    except Exception as e:
        return json.dumps({"error": f"data_json 파싱 실패: {e}"}, ensure_ascii=False)

    if not rows:
        return json.dumps({"error": "데이터가 없습니다"}, ensure_ascii=False)

    numeric_cols, categorical_cols = _classify_columns(rows)

    # X축
    if x_key_hint and x_key_hint in (numeric_cols + categorical_cols):
        x_key = x_key_hint
        x_type = "categorical" if x_key in categorical_cols else "numeric"
    else:
        x_key, x_type = _pick_x_key(numeric_cols, categorical_cols, intent)

    # Y축
    y_keys: list[str] = list(y_keys_hint) if y_keys_hint else []
    if not y_keys:
        y_keys = [c for c in numeric_cols if c != x_key][:6]
    if not y_keys:
        y_keys = [c for c in numeric_cols][:6]

    # 차트 타입
    chart_type = chart_type_hint
    if chart_type not in ("line", "bar", "scatter"):
        chart_type = _pick_chart_type(intent, x_type)

    # 수치 통계 (프론트 요약 카드용)
    stats: dict = {}
    for col in y_keys:
        vals = [
            float(r[col])
            for r in rows
            if r.get(col) is not None and isinstance(r.get(col), (int, float))
        ]
        if len(vals) >= 2:
            stats[col] = {
                "min": round(min(vals), 4),
                "max": round(max(vals), 4),
                "avg": round(statistics.mean(vals), 4),
                "stdev": round(statistics.stdev(vals), 4),
            }

    result = {
        "chartType": chart_type,
        "xKey": x_key,
        "yKeys": y_keys,
        "title": intent[:60] if intent else "데이터 차트",
        "stats": stats,
        "row_count": len(rows),
    }

    elapsed_ms = (time.monotonic() - started_at) * 1000
    logger.info(
        f"[chart_build_tool] 완료 elapsed_ms={elapsed_ms:.1f} "
        f"chartType={chart_type} xKey={x_key} yKeys={y_keys[:3]}"
    )
    return json.dumps(result, ensure_ascii=False)
