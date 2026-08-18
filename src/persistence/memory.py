from __future__ import annotations

from collections import defaultdict
from dataclasses import replace
from threading import Lock
from typing import Generic, TypeVar

from src.domain.models import (
    Assessment,
    Delivery,
    Narrative,
    NormalizedApplication,
    RawFormSubmission,
    Report,
    SubmissionState,
)


class InMemoryRawFormSubmissionRepository:
    def __init__(self) -> None:
        self._by_submission_id: dict[str, RawFormSubmission] = {}
        self._by_response_key: dict[tuple[str, str], str] = {}

    def insert(self, submission: RawFormSubmission) -> bool:
        response_key = (submission.form_id, submission.response_id)
        if response_key in self._by_response_key:
            return False
        self._by_submission_id[submission.submission_id] = submission
        self._by_response_key[response_key] = submission.submission_id
        return True

    def get(self, submission_id: str) -> RawFormSubmission | None:
        return self._by_submission_id.get(submission_id)

    def find_by_response(self, form_id: str, response_id: str) -> RawFormSubmission | None:
        submission_id = self._by_response_key.get((form_id, response_id))
        if submission_id is None:
            return None
        return self._by_submission_id[submission_id]


T = TypeVar("T")


class _SingleValueRepository(Generic[T]):
    def __init__(self) -> None:
        self._store: dict[str, list[T]] = defaultdict(list)

    def insert(self, value: T) -> None:
        self._store[value.submission_id].append(value)

    def get(self, submission_id: str) -> T | None:
        values = self._store.get(submission_id, [])
        return values[-1] if values else None

    def list_for_submission(self, submission_id: str) -> list[T]:
        return list(self._store.get(submission_id, []))


class InMemoryNarrativeRepository:
    def __init__(self) -> None:
        self._store: dict[str, list[Narrative]] = defaultdict(list)

    def insert(self, narrative: Narrative) -> None:
        self._store[narrative.submission_id].append(narrative)

    def list_for_submission(self, submission_id: str) -> list[Narrative]:
        return list(self._store.get(submission_id, []))

    def get_latest(self, submission_id: str) -> Narrative | None:
        values = self._store.get(submission_id, [])
        return values[-1] if values else None


class InMemoryReportRepository:
    def __init__(self) -> None:
        self._store: dict[str, list[Report]] = defaultdict(list)

    def insert(self, report: Report) -> None:
        self._store[report.submission_id].append(report)

    def list_for_submission(self, submission_id: str) -> list[Report]:
        return list(self._store.get(submission_id, []))

    def get_by_type(self, submission_id: str) -> dict[str, Report]:
        return {report.report_type.value: report for report in self._store.get(submission_id, [])}


class InMemoryDeliveryRepository:
    def __init__(self) -> None:
        self._store: dict[str, list[Delivery]] = defaultdict(list)

    def insert(self, delivery: Delivery) -> None:
        self._store[delivery.submission_id].append(delivery)

    def list_for_submission(self, submission_id: str) -> list[Delivery]:
        return list(self._store.get(submission_id, []))


class InMemorySubmissionStateRepository:
    def __init__(self) -> None:
        self._store: dict[str, SubmissionState] = {}
        self._lock = Lock()

    def create(self, state: SubmissionState) -> None:
        with self._lock:
            self._store[state.submission_id] = state

    def get(self, submission_id: str) -> SubmissionState | None:
        with self._lock:
            state = self._store.get(submission_id)
        if state is None:
            return None
        return replace(state, attempt_counts=dict(state.attempt_counts))

    def compare_and_set(
        self,
        submission_id: str,
        *,
        expected_state: SubmissionState,
        new_state: SubmissionState,
    ) -> bool:
        with self._lock:
            current = self._store.get(submission_id)
            if current is None or current != expected_state:
                return False
            self._store[submission_id] = replace(new_state, attempt_counts=dict(new_state.attempt_counts))
            return True


class InMemoryRepositories:
    def __init__(self) -> None:
        self.raw_submissions = InMemoryRawFormSubmissionRepository()
        self.normalized_applications = _SingleValueRepository[NormalizedApplication]()
        self.assessments = _SingleValueRepository[Assessment]()
        self.narratives = InMemoryNarrativeRepository()
        self.reports = InMemoryReportRepository()
        self.deliveries = InMemoryDeliveryRepository()
        self.submission_states = InMemorySubmissionStateRepository()
