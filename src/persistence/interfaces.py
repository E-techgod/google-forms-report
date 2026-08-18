from __future__ import annotations

from typing import Protocol

from src.domain.models import (
    Assessment,
    Delivery,
    Narrative,
    NormalizedApplication,
    RawFormSubmission,
    Report,
    SubmissionState,
)


class RawFormSubmissionRepository(Protocol):
    def insert(self, submission: RawFormSubmission) -> bool:
        ...

    def get(self, submission_id: str) -> RawFormSubmission | None:
        ...

    def find_by_response(self, form_id: str, response_id: str) -> RawFormSubmission | None:
        ...


class NormalizedApplicationRepository(Protocol):
    def insert(self, application: NormalizedApplication) -> None:
        ...

    def get(self, submission_id: str) -> NormalizedApplication | None:
        ...

    def list_for_submission(self, submission_id: str) -> list[NormalizedApplication]:
        ...


class AssessmentRepository(Protocol):
    def insert(self, assessment: Assessment) -> None:
        ...

    def get(self, submission_id: str) -> Assessment | None:
        ...

    def list_for_submission(self, submission_id: str) -> list[Assessment]:
        ...


class NarrativeRepository(Protocol):
    def insert(self, narrative: Narrative) -> None:
        ...

    def list_for_submission(self, submission_id: str) -> list[Narrative]:
        ...

    def get_latest(self, submission_id: str) -> Narrative | None:
        ...


class ReportRepository(Protocol):
    def insert(self, report: Report) -> None:
        ...

    def list_for_submission(self, submission_id: str) -> list[Report]:
        ...

    def get_by_type(self, submission_id: str) -> dict[str, Report]:
        ...


class DeliveryRepository(Protocol):
    def insert(self, delivery: Delivery) -> None:
        ...

    def list_for_submission(self, submission_id: str) -> list[Delivery]:
        ...


class SubmissionStateRepository(Protocol):
    def create(self, state: SubmissionState) -> None:
        ...

    def get(self, submission_id: str) -> SubmissionState | None:
        ...

    def compare_and_set(
        self,
        submission_id: str,
        *,
        expected_state: SubmissionState,
        new_state: SubmissionState,
    ) -> bool:
        ...


class RepositoryBundle(Protocol):
    raw_submissions: RawFormSubmissionRepository
    normalized_applications: NormalizedApplicationRepository
    assessments: AssessmentRepository
    narratives: NarrativeRepository
    reports: ReportRepository
    deliveries: DeliveryRepository
    submission_states: SubmissionStateRepository
