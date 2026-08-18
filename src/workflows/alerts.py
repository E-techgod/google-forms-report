from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from src.domain.models import PipelineStage


@dataclass(frozen=True)
class AlertEvent:
    submission_id: str
    stage: PipelineStage
    reason_code: str
    message: str
    emitted_at: datetime


class AlertSink(Protocol):
    def send(self, event: AlertEvent) -> None:
        ...


class InMemoryAlertSink:
    def __init__(self) -> None:
        self.events: list[AlertEvent] = []

    def send(self, event: AlertEvent) -> None:
        self.events.append(event)
