from collections import deque
from typing import Deque, Dict, Iterable, List, Optional

from nova_backend.runtime.events import RuntimeEvent


class TelemetryStore:
    """In-memory private telemetry ring buffer.

    This is intentionally internal/admin-only. It gives Phase 2.5 private
    observability without committing to a database schema too early.
    """

    def __init__(self, max_events: int = 1000) -> None:
        self._events: Deque[RuntimeEvent] = deque(maxlen=max_events)

    def record(self, event: RuntimeEvent) -> None:
        self._events.append(event)

    def extend(self, events: Iterable[RuntimeEvent]) -> None:
        for event in events:
            self.record(event)

    def recent(self, limit: int = 100, trace_id: Optional[str] = None) -> List[Dict]:
        events = list(self._events)
        if trace_id:
            events = [event for event in events if event.trace_id == trace_id]
        return [event.private_dict() for event in events[-limit:]]

    def summary(self) -> Dict:
        counts: Dict[str, int] = {}
        for event in self._events:
            counts[event.type] = counts.get(event.type, 0) + 1
        return {
            "stored_events": len(self._events),
            "event_counts": counts,
        }
