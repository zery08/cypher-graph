"""
채팅 관련 스키마 정의
"""
from pydantic import BaseModel
from typing import Any, Literal


class ChatAction(BaseModel):
    type: Literal[
        "apply_query",
        "open_tab",
        "focus_node",
        "select_row",
        "set_filters",
        "create_chart",
        "highlight_series",
    ]
    # 각 action type별 페이로드
    tab: str | None = None
    node_id: str | None = None
    query: str | None = None
    row_id: str | None = None
    filters: dict[str, Any] | None = None
    chart_config: dict[str, Any] | None = None
    series_id: str | None = None


class ChatMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str


class ChatRequest(BaseModel):
    message: str
    history: list[ChatMessage] = []
    context: dict[str, Any] = {}


class ToolResult(BaseModel):
    graph: Any | None = None
    table: Any | None = None
    chart: Any | None = None
    cypher: str | None = None
    summary: str | None = None


class StepInfo(BaseModel):
    tool: str        # tool 이름 (human-readable)
    tool_key: str    # 실제 함수 이름
    input: str       # LLM이 tool에 전달한 입력
    output: str      # tool 실행 결과 요약


class ChatResponse(BaseModel):
    message: str
    actions: list[ChatAction] = []
    tool_results: ToolResult = ToolResult()
    steps: list[StepInfo] = []
    thinking: str | None = None
