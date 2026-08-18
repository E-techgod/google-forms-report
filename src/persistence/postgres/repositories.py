from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import create_engine, desc, select, update
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from src.domain.models import (
    Assessment,
    Delivery,
    DeliveryStatus,
    Narrative,
    NormalizedApplication,
    RawFormSubmission,
    Report,
    ReportType,
    SubmissionState,
    SubmissionStatus,
)

from .models import (
    AssessmentRow,
    DeliveryRow,
    NarrativeRow,
    NormalizedApplicationRow,
    RawFormSubmissionRow,
    ReportRow,
    SubmissionStateRow,
)
from .serializers import (
    deserialize_attempt_counts,
    deserialize_stage_error,
    serialize_attempt_counts,
    serialize_delivery_status,
    serialize_report_type,
    serialize_stage_error,
    serialize_submission_status,
)


class PostgresRawFormSubmissionRepository:
    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self._session_factory = session_factory

    def insert(self, submission: RawFormSubmission) -> bool:
        with self._session_factory.begin() as session:
            existing = session.get(RawFormSubmissionRow, submission.submission_id)
            if existing is not None:
                return False
            response_match = session.execute(
                select(RawFormSubmissionRow.submission_id).where(
                    RawFormSubmissionRow.form_id == submission.form_id,
                    RawFormSubmissionRow.response_id == submission.response_id,
                )
            ).scalar_one_or_none()
            if response_match is not None:
                return False
            session.add(
                RawFormSubmissionRow(
                    submission_id=submission.submission_id,
                    form_id=submission.form_id,
                    response_id=submission.response_id,
                    received_at=submission.received_at,
                    raw_payload=submission.raw_payload,
                    form_schema_version_at_receipt=submission.form_schema_version_at_receipt,
                )
            )
            return True

    def get(self, submission_id: str) -> RawFormSubmission | None:
        with self._session_factory() as session:
            row = session.get(RawFormSubmissionRow, submission_id)
            return None if row is None else _to_raw_form_submission(row)

    def find_by_response(self, form_id: str, response_id: str) -> RawFormSubmission | None:
        with self._session_factory() as session:
            row = session.execute(
                select(RawFormSubmissionRow).where(
                    RawFormSubmissionRow.form_id == form_id,
                    RawFormSubmissionRow.response_id == response_id,
                )
            ).scalar_one_or_none()
            return None if row is None else _to_raw_form_submission(row)


class PostgresNormalizedApplicationRepository:
    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self._session_factory = session_factory

    def insert(self, application: NormalizedApplication) -> None:
        with self._session_factory.begin() as session:
            session.add(
                NormalizedApplicationRow(
                    submission_id=application.submission_id,
                    form_schema_version=application.form_schema_version,
                    fields=application.fields,
                    normalization_warnings=list(application.normalization_warnings),
                )
            )

    def get(self, submission_id: str) -> NormalizedApplication | None:
        with self._session_factory() as session:
            row = session.execute(
                select(NormalizedApplicationRow)
                .where(NormalizedApplicationRow.submission_id == submission_id)
                .order_by(desc(NormalizedApplicationRow.id))
                .limit(1)
            ).scalar_one_or_none()
            return None if row is None else _to_normalized_application(row)

    def list_for_submission(self, submission_id: str) -> list[NormalizedApplication]:
        with self._session_factory() as session:
            rows = session.execute(
                select(NormalizedApplicationRow)
                .where(NormalizedApplicationRow.submission_id == submission_id)
                .order_by(NormalizedApplicationRow.id)
            ).scalars()
            return [_to_normalized_application(row) for row in rows]


class PostgresAssessmentRepository:
    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self._session_factory = session_factory

    def insert(self, assessment: Assessment) -> None:
        with self._session_factory.begin() as session:
            session.add(
                AssessmentRow(
                    submission_id=assessment.submission_id,
                    rule_version=assessment.rule_version,
                    rules_evaluated=list(assessment.rules_evaluated),
                    rules_triggered=list(assessment.rules_triggered),
                    reasons=list(assessment.reasons),
                    qualification=assessment.qualification,
                    classified_at=assessment.classified_at,
                )
            )

    def get(self, submission_id: str) -> Assessment | None:
        with self._session_factory() as session:
            row = session.execute(
                select(AssessmentRow)
                .where(AssessmentRow.submission_id == submission_id)
                .order_by(desc(AssessmentRow.id))
                .limit(1)
            ).scalar_one_or_none()
            return None if row is None else _to_assessment(row)

    def list_for_submission(self, submission_id: str) -> list[Assessment]:
        with self._session_factory() as session:
            rows = session.execute(
                select(AssessmentRow)
                .where(AssessmentRow.submission_id == submission_id)
                .order_by(AssessmentRow.id)
            ).scalars()
            return [_to_assessment(row) for row in rows]


class PostgresNarrativeRepository:
    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self._session_factory = session_factory

    def insert(self, narrative: Narrative) -> None:
        with self._session_factory.begin() as session:
            session.add(
                NarrativeRow(
                    submission_id=narrative.submission_id,
                    attempt_number=narrative.attempt_number,
                    provider=narrative.provider,
                    model=narrative.model,
                    prompt_version=narrative.prompt_version,
                    raw_output=narrative.raw_output,
                    validation_result=narrative.validation_result,
                    text=narrative.text,
                    generated_at=narrative.generated_at,
                    used_fallback=narrative.used_fallback,
                )
            )

    def list_for_submission(self, submission_id: str) -> list[Narrative]:
        with self._session_factory() as session:
            rows = session.execute(
                select(NarrativeRow)
                .where(NarrativeRow.submission_id == submission_id)
                .order_by(NarrativeRow.id)
            ).scalars()
            return [_to_narrative(row) for row in rows]

    def get_latest(self, submission_id: str) -> Narrative | None:
        with self._session_factory() as session:
            row = session.execute(
                select(NarrativeRow)
                .where(NarrativeRow.submission_id == submission_id)
                .order_by(desc(NarrativeRow.id))
                .limit(1)
            ).scalar_one_or_none()
            return None if row is None else _to_narrative(row)


class PostgresReportRepository:
    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self._session_factory = session_factory

    def insert(self, report: Report) -> None:
        with self._session_factory.begin() as session:
            session.add(
                ReportRow(
                    submission_id=report.submission_id,
                    report_type=serialize_report_type(report.report_type),
                    template_version=report.template_version,
                    artifact_ref=report.artifact_ref,
                    content=report.content,
                    generated_at=report.generated_at,
                )
            )

    def list_for_submission(self, submission_id: str) -> list[Report]:
        with self._session_factory() as session:
            rows = session.execute(
                select(ReportRow)
                .where(ReportRow.submission_id == submission_id)
                .order_by(ReportRow.id)
            ).scalars()
            return [_to_report(row) for row in rows]

    def get_by_type(self, submission_id: str) -> dict[str, Report]:
        reports = self.list_for_submission(submission_id)
        return {report.report_type.value: report for report in reports}


class PostgresDeliveryRepository:
    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self._session_factory = session_factory

    def insert(self, delivery: Delivery) -> None:
        with self._session_factory.begin() as session:
            session.add(
                DeliveryRow(
                    submission_id=delivery.submission_id,
                    report_type=serialize_report_type(delivery.report_type),
                    recipient=delivery.recipient,
                    delivery_key=delivery.delivery_key,
                    attempt_number=delivery.attempt_number,
                    status=serialize_delivery_status(delivery.status),
                    message_id=delivery.message_id,
                    attempted_at=delivery.attempted_at,
                    sent_at=delivery.sent_at,
                    error_code=delivery.error_code,
                )
            )

    def list_for_submission(self, submission_id: str) -> list[Delivery]:
        with self._session_factory() as session:
            rows = session.execute(
                select(DeliveryRow)
                .where(DeliveryRow.submission_id == submission_id)
                .order_by(DeliveryRow.id)
            ).scalars()
            return [_to_delivery(row) for row in rows]


class PostgresSubmissionStateRepository:
    def __init__(self, engine: Engine, session_factory: sessionmaker[Session]) -> None:
        self._engine = engine
        self._session_factory = session_factory

    def create(self, state: SubmissionState) -> None:
        with self._session_factory.begin() as session:
            session.add(
                SubmissionStateRow(
                    submission_id=state.submission_id,
                    status=serialize_submission_status(state.status),
                    attempt_counts=serialize_attempt_counts(state.attempt_counts),
                    last_error=serialize_stage_error(state.last_error),
                    updated_at=state.updated_at,
                )
            )

    def get(self, submission_id: str) -> SubmissionState | None:
        with self._session_factory() as session:
            row = session.get(SubmissionStateRow, submission_id)
            return None if row is None else _to_submission_state(row)

    def compare_and_set(
        self,
        submission_id: str,
        *,
        expected_state: SubmissionState,
        new_state: SubmissionState,
    ) -> bool:
        expected_attempt_counts = serialize_attempt_counts(expected_state.attempt_counts)
        expected_last_error = serialize_stage_error(expected_state.last_error)
        conditions = [
            SubmissionStateRow.submission_id == submission_id,
            SubmissionStateRow.status == serialize_submission_status(expected_state.status),
            SubmissionStateRow.attempt_counts == expected_attempt_counts,
        ]
        if expected_last_error is None:
            conditions.append(SubmissionStateRow.last_error.is_(None))
        else:
            conditions.append(SubmissionStateRow.last_error == expected_last_error)
        statement = (
            update(SubmissionStateRow)
            .where(*conditions)
            .values(
                status=serialize_submission_status(new_state.status),
                attempt_counts=serialize_attempt_counts(new_state.attempt_counts),
                last_error=serialize_stage_error(new_state.last_error),
                updated_at=new_state.updated_at,
            )
        )
        with self._engine.begin() as connection:
            result = connection.execute(statement)
            return result.rowcount == 1


@dataclass
class PostgresRepositories:
    database_url: str

    def __post_init__(self) -> None:
        self._engine = create_engine(self.database_url, future=True)
        self._session_factory = sessionmaker(self._engine, expire_on_commit=False)
        self.raw_submissions = PostgresRawFormSubmissionRepository(self._session_factory)
        self.normalized_applications = PostgresNormalizedApplicationRepository(self._session_factory)
        self.assessments = PostgresAssessmentRepository(self._session_factory)
        self.narratives = PostgresNarrativeRepository(self._session_factory)
        self.reports = PostgresReportRepository(self._session_factory)
        self.deliveries = PostgresDeliveryRepository(self._session_factory)
        self.submission_states = PostgresSubmissionStateRepository(self._engine, self._session_factory)

    def dispose(self) -> None:
        self._engine.dispose()


def _to_raw_form_submission(row: RawFormSubmissionRow) -> RawFormSubmission:
    return RawFormSubmission(
        submission_id=row.submission_id,
        form_id=row.form_id,
        response_id=row.response_id,
        received_at=row.received_at,
        raw_payload=dict(row.raw_payload),
        form_schema_version_at_receipt=row.form_schema_version_at_receipt,
    )


def _to_normalized_application(row: NormalizedApplicationRow) -> NormalizedApplication:
    return NormalizedApplication(
        submission_id=row.submission_id,
        form_schema_version=row.form_schema_version,
        fields=dict(row.fields),
        normalization_warnings=tuple(row.normalization_warnings),
    )


def _to_assessment(row: AssessmentRow) -> Assessment:
    return Assessment(
        submission_id=row.submission_id,
        rule_version=row.rule_version,
        rules_evaluated=tuple(row.rules_evaluated),
        rules_triggered=tuple(row.rules_triggered),
        reasons=tuple(row.reasons),
        qualification=row.qualification,
        classified_at=row.classified_at,
    )


def _to_narrative(row: NarrativeRow) -> Narrative:
    return Narrative(
        submission_id=row.submission_id,
        attempt_number=row.attempt_number,
        provider=row.provider,
        model=row.model,
        prompt_version=row.prompt_version,
        raw_output=row.raw_output,
        validation_result=row.validation_result,
        text=row.text,
        generated_at=row.generated_at,
        used_fallback=row.used_fallback,
    )


def _to_report(row: ReportRow) -> Report:
    return Report(
        submission_id=row.submission_id,
        report_type=ReportType(row.report_type),
        template_version=row.template_version,
        artifact_ref=row.artifact_ref,
        content=bytes(row.content),
        generated_at=row.generated_at,
    )


def _to_delivery(row: DeliveryRow) -> Delivery:
    return Delivery(
        submission_id=row.submission_id,
        report_type=ReportType(row.report_type),
        recipient=row.recipient,
        delivery_key=row.delivery_key,
        attempt_number=row.attempt_number,
        status=DeliveryStatus(row.status),
        message_id=row.message_id,
        attempted_at=row.attempted_at,
        sent_at=row.sent_at,
        error_code=row.error_code,
    )


def _to_submission_state(row: SubmissionStateRow) -> SubmissionState:
    return SubmissionState(
        submission_id=row.submission_id,
        status=SubmissionStatus(row.status),
        attempt_counts=deserialize_attempt_counts(row.attempt_counts),
        last_error=deserialize_stage_error(row.last_error),
        updated_at=row.updated_at,
    )
