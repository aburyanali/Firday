from dataclasses import dataclass, field
from time import time
from typing import Dict, Literal, Optional
from uuid import uuid4


TaskState = Literal["queued", "running", "cancel_requested", "completed", "failed"]


@dataclass
class RuntimeTask:
    kind: str
    trace_id: str
    session_id: str
    task_id: str = field(default_factory=lambda: uuid4().hex)
    state: TaskState = "queued"
    created_at: float = field(default_factory=time)
    updated_at: float = field(default_factory=time)
    summary: str = ""
    error: Optional[str] = None

    def transition(self, state: TaskState, error: Optional[str] = None) -> None:
        self.state = state
        self.updated_at = time()
        self.error = error

    def snapshot(self) -> Dict:
        return {
            "task_id": self.task_id,
            "kind": self.kind,
            "trace_id": self.trace_id,
            "session_id": self.session_id,
            "state": self.state,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "summary": self.summary,
            "error": self.error,
        }


class TaskManager:
    def __init__(self) -> None:
        self._tasks: Dict[str, RuntimeTask] = {}

    def create(self, kind: str, trace_id: str, session_id: str, summary: str = "") -> RuntimeTask:
        task = RuntimeTask(kind=kind, trace_id=trace_id, session_id=session_id, summary=summary)
        self._tasks[task.task_id] = task
        return task

    def get(self, task_id: str) -> Optional[RuntimeTask]:
        return self._tasks.get(task_id)

    def snapshots(self):
        return [task.snapshot() for task in self._tasks.values()]
