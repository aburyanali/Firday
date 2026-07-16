from typing import Iterable, Optional

from nova_backend.runtime.events import RuntimeEvent
from nova_backend.runtime.sessions import SessionManager
from nova_backend.runtime.state import RuntimeState
from nova_backend.runtime.tasks import TaskManager
from nova_backend.runtime.telemetry import TelemetryStore


class RuntimeService:
    def __init__(self) -> None:
        self.state = RuntimeState()
        self.sessions = SessionManager()
        self.tasks = TaskManager()
        self.telemetry = TelemetryStore()

    def record(self, event: RuntimeEvent) -> RuntimeEvent:
        self.telemetry.record(event)
        return event

    def record_many(self, events: Iterable[RuntimeEvent]) -> None:
        self.telemetry.extend(events)

    def snapshot(self, session_id: Optional[str] = None):
        session = self.sessions.get(session_id) if session_id else None
        return {
            "assistant": self.state.snapshot(),
            "session": session.snapshot() if session else None,
            "sessions": self.sessions.snapshots(),
            "tasks": self.tasks.snapshots(),
            "telemetry": self.telemetry.summary(),
        }


runtime_service = RuntimeService()
