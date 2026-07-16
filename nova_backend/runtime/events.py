from dataclasses import dataclass, field
from time import time
from typing import Any, Dict, Literal, Optional
from uuid import uuid4


EventVisibility = Literal["public", "private"]


PUBLIC_EVENT_TYPES = {
    "assistant.boot",
    "assistant.ready",
    "assistant.status",
    "assistant.intent",
    "assistant.reasoning",
    "assistant.memory",
    "assistant.tool_call",
    "assistant.tool_result",
    "assistant.planning",
    "assistant.voice",
    "assistant.token",
    "assistant.message",
    "assistant.error",
    "assistant.provider",
    "assistant.failover",
    "assistant.degraded",
    "assistant.shutdown",
    "assistant.listening",
    "assistant.processing",
    "assistant.speaking",
    "assistant.interrupted",
    "assistant.task_started",
    "assistant.task_completed",
    "assistant.warning",
    "assistant.recovering",
    "task.created",
    "task.updated",
    "task.completed",
    "task.failed",
}


@dataclass(frozen=True)
class RuntimeEvent:
    type: str
    trace_id: str
    session_id: str
    payload: Dict[str, Any] = field(default_factory=dict)
    visibility: EventVisibility = "public"
    event_id: str = field(default_factory=lambda: uuid4().hex)
    timestamp: float = field(default_factory=time)

    def public_dict(self) -> Dict[str, Any]:
        payload = self.payload if self.visibility == "public" else {"message": "private event"}
        return {
            "type": self.type,
            "event_id": self.event_id,
            "trace_id": self.trace_id,
            "session_id": self.session_id,
            "timestamp": self.timestamp,
            "payload": payload,
        }

    def private_dict(self) -> Dict[str, Any]:
        return {
            "type": self.type,
            "event_id": self.event_id,
            "trace_id": self.trace_id,
            "session_id": self.session_id,
            "timestamp": self.timestamp,
            "visibility": self.visibility,
            "payload": self.payload,
        }


def public_event(
    event_type: str,
    trace_id: str,
    session_id: str,
    payload: Optional[Dict[str, Any]] = None,
) -> RuntimeEvent:
    return RuntimeEvent(
        type=event_type,
        trace_id=trace_id,
        session_id=session_id,
        payload=payload or {},
        visibility="public",
    )


def private_event(
    event_type: str,
    trace_id: str,
    session_id: str,
    payload: Optional[Dict[str, Any]] = None,
) -> RuntimeEvent:
    return RuntimeEvent(
        type=event_type,
        trace_id=trace_id,
        session_id=session_id,
        payload=payload or {},
        visibility="private",
    )
