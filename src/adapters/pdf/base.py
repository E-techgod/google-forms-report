from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from typing import Protocol

from src.config.models import ReportTemplate
from src.domain.models import ClientReportContext, InternalReportContext


@dataclass(frozen=True)
class RenderedArtifact:
    artifact_ref: str
    content: bytes


class ReportRendererError(Exception):
    pass


class ReportRenderer(Protocol):
    def render(
        self,
        *,
        context: InternalReportContext | ClientReportContext,
        template: ReportTemplate,
    ) -> RenderedArtifact:
        ...


class FakeReportRenderer:
    def __init__(self) -> None:
        self._failures: deque[Exception] = deque()
        self.calls = 0

    def fail_next_call(self, error: Exception) -> None:
        self._failures.append(error)

    def render(
        self,
        *,
        context: InternalReportContext | ClientReportContext,
        template: ReportTemplate,
    ) -> RenderedArtifact:
        self.calls += 1
        if self._failures:
            raise self._failures.popleft()
        body = f"{template.report_type.value}:{template.version}:{context.submission_id}"
        return RenderedArtifact(
            artifact_ref=f"{context.submission_id}-{template.report_type.value.lower()}-{template.version}",
            content=body.encode("utf-8"),
        )
