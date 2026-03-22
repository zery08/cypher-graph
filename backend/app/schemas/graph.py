"""
그래프 관련 스키마 정의
"""
from pydantic import BaseModel
from typing import Any


class GraphNode(BaseModel):
    id: str
    labels: list[str]
    properties: dict[str, Any]


class GraphEdge(BaseModel):
    id: str
    type: str
    source: str
    target: str
    properties: dict[str, Any]


class GraphResult(BaseModel):
    nodes: list[GraphNode] = []
    edges: list[GraphEdge] = []
    raw: list[dict[str, Any]] = []


class QueryRequest(BaseModel):
    query: str
    parameters: dict[str, Any] = {}


class QueryResponse(BaseModel):
    result: GraphResult
    cypher: str
    row_count: int
    execution_time_ms: float | None = None


class SchemaResponse(BaseModel):
    node_labels: list[str]
    relationship_types: list[str]
    properties: dict[str, list[str]]
    raw_schema: str | None = None
