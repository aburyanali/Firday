from dataclasses import dataclass, field
from time import time
from typing import Literal


AssistantState = Literal[
    "offline",
    "booting",
    "ready",
    "idle",
    "listening",
    "thinking",
    "planning",
    "executing",
    "speaking",
    "processing",
    "interrupted",
    "warning",
    "recovering",
    "error",
    "shutdown",
]


@dataclass
class RuntimeState:
    state: AssistantState = "offline"
    last_changed_at: float = field(default_factory=time)

    def transition(self, next_state: AssistantState) -> AssistantState:
        self.state = next_state
        self.last_changed_at = time()
        return self.state

    def snapshot(self):
        return {
            "state": self.state,
            "last_changed_at": self.last_changed_at,
        }
