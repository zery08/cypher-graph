"""
공통 응답 스키마
"""
from pydantic import BaseModel
from typing import Any


class ErrorResponse(BaseModel):
    detail: str
    code: str | None = None


class HealthResponse(BaseModel):
    status: str
    neo4j_connected: bool
    version: str = "1.0.0"
