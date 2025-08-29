from collections import deque
from typing import Any, Deque, Dict, Optional


class WorkItem:
    def __init__(self, kind: str, payload: Dict[str, Any]):
        self.kind = kind
        self.payload = payload


class Coordinator:
    def __init__(self) -> None:
        self.queue: Deque[WorkItem] = deque()

    def enqueue(self, kind: str, payload: Dict[str, Any]) -> None:
        self.queue.append(WorkItem(kind, payload))

    def next(self) -> Optional[WorkItem]:
        return self.queue.popleft() if self.queue else None

