from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from datetime import datetime
from typing import Callable, Protocol

from src.domain.models import Report


@dataclass(frozen=True)
class DeliveryReceipt:
    message_id: str
    delivery_key: str
    sent_at: datetime
    recipient: str


class EmailSenderError(Exception):
    pass


class EmailSender(Protocol):
    def find_existing(self, delivery_key: str) -> DeliveryReceipt | None:
        ...

    def send(self, *, report: Report, recipient: str, delivery_key: str) -> DeliveryReceipt:
        ...


class FakeEmailSender:
    def __init__(self, *, now_factory: Callable[[], datetime] | None = None) -> None:
        self._failures: deque[Exception] = deque()
        self._now_factory = now_factory or datetime.utcnow
        self._sent: dict[str, DeliveryReceipt] = {}
        self.calls = 0

    def fail_next_call(self, error: Exception) -> None:
        self._failures.append(error)

    def find_existing(self, delivery_key: str) -> DeliveryReceipt | None:
        return self._sent.get(delivery_key)

    def send(self, *, report: Report, recipient: str, delivery_key: str) -> DeliveryReceipt:
        self.calls += 1
        if self._failures:
            raise self._failures.popleft()
        existing = self.find_existing(delivery_key)
        if existing is not None:
            return existing
        receipt = DeliveryReceipt(
            message_id=f"msg-{len(self._sent) + 1}",
            delivery_key=delivery_key,
            sent_at=self._now_factory(),
            recipient=recipient,
        )
        self._sent[delivery_key] = receipt
        return receipt
