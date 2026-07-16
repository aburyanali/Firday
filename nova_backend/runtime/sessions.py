from dataclasses import dataclass, field
from time import time
from typing import Dict, List, Optional
from uuid import uuid4


@dataclass
class RuntimeSession:
    session_id: str
    user_id: str = "user_default"
    created_at: float = field(default_factory=time)
    updated_at: float = field(default_factory=time)
    turn_count: int = 0
    last_trace_id: Optional[str] = None
    messages: List[Dict[str, str]] = field(default_factory=list)

    def touch(self, trace_id: str) -> None:
        self.updated_at = time()
        self.turn_count += 1
        self.last_trace_id = trace_id

    def snapshot(self) -> Dict:
        return {
            "session_id": self.session_id,
            "user_id": self.user_id,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "turn_count": self.turn_count,
            "last_trace_id": self.last_trace_id,
            "recent_messages": self.messages[-8:],
        }

    def remember(self, role: str, content: str) -> None:
        cleaned = " ".join(content.strip().split())
        if not cleaned:
            return
        self.messages.append({"role": role, "content": cleaned[:1200]})
        self.messages = self.messages[-12:]

    def context_prompt(self, limit: int = 6) -> str:
        lines = []
        for message in self.messages[-limit:]:
            label = "User" if message["role"] == "user" else "NOVA"
            lines.append(f"{label}: {message['content']}")
        return "\n".join(lines)


class SessionManager:
    def __init__(self) -> None:
        self._sessions: Dict[str, RuntimeSession] = {}

    def get_or_create(self, session_id: Optional[str] = None, user_id: str = "user_default") -> RuntimeSession:
        resolved_id = session_id or uuid4().hex
        if resolved_id not in self._sessions:
            self._sessions[resolved_id] = RuntimeSession(session_id=resolved_id, user_id=user_id)
        return self._sessions[resolved_id]

    def get(self, session_id: str) -> Optional[RuntimeSession]:
        return self._sessions.get(session_id)

    def snapshots(self):
        return [session.snapshot() for session in self._sessions.values()]
