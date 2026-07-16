from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field


class HealthResponse(BaseModel):
    status: Literal["ok", "degraded"]
    app: str
    environment: str
    services: Dict[str, Any]


class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1)
    session_id: Optional[str] = None
    user_id: str = "user_default"
    stream: bool = False


class ChatResponse(BaseModel):
    trace_id: str
    session_id: str
    response: str
    intent: str
    confidence: float
    events: List[Dict[str, Any]]


class StreamEvent(BaseModel):
    type: str
    trace_id: str
    payload: Dict[str, Any] = Field(default_factory=dict)
