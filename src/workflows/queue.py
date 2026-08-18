from __future__ import annotations

from collections import deque


class InMemoryTaskQueue:
    def __init__(self) -> None:
        self._queue: deque[str] = deque()

    def enqueue(self, submission_id: str) -> None:
        self._queue.append(submission_id)

    def pop(self) -> str | None:
        return self._queue.popleft() if self._queue else None

    def __len__(self) -> int:
        return len(self._queue)
