from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta
from threading import Barrier, Event, Thread

from sqlalchemy import create_engine, event, func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.exc import IntegrityError

import pytest

from src.domain.models import (
    Assessment,
    Delivery,
    DeliveryStatus,
    Narrative,
    NormalizedApplication,
    PipelineStage,
    RawFormSubmission,
    Report,
    ReportType,
    StageError,
    SubmissionState,
    SubmissionStatus,
)
from src.persistence.postgres.models import RawFormSubmissionRow


def _raw_submission(submission_id: str = "submission-1") -> RawFormSubmission:
    return RawFormSubmission(
        submission_id=submission_id,
        form_id="demo-form",
        response_id=f"response-{submission_id}",
        received_at=datetime(2026, 8, 18, 9, 0, 0),
        raw_payload={"name": "test-applicant-001", "age": 42, "consent": True},
        form_schema_version_at_receipt="schema-v1",
    )


def _normalized(submission_id: str = "submission-1", warnings: tuple[str, ...] = ()) -> NormalizedApplication:
    return NormalizedApplication(
        submission_id=submission_id,
        form_schema_version="schema-v1",
        fields={"applicant_name": "test-applicant-001", "age": 42, "eligible": True},
        normalization_warnings=warnings,
    )


def _assessment(submission_id: str = "submission-1", reasons: tuple[str, ...] = ("Synthetic reason",)) -> Assessment:
    return Assessment(
        submission_id=submission_id,
        rule_version="rules-v1",
        rules_evaluated=("RULE-1", "RULE-2"),
        rules_triggered=("RULE-2",),
        reasons=reasons,
        qualification="REVIEW",
        classified_at=datetime(2026, 8, 18, 9, 5, 0),
    )


def _narrative(submission_id: str = "submission-1", attempt_number: int = 1, text: str = "Narrative") -> Narrative:
    return Narrative(
        submission_id=submission_id,
        attempt_number=attempt_number,
        provider="null-llm",
        model="template-only",
        prompt_version="prompt-v1",
        raw_output='{"text":"Narrative"}',
        validation_result="OK",
        text=text,
        generated_at=datetime(2026, 8, 18, 9, 10, 0) + timedelta(minutes=attempt_number),
        used_fallback=attempt_number > 1,
    )


def _report(submission_id: str = "submission-1", report_type: ReportType = ReportType.CLIENT, ref_suffix: str = "a") -> Report:
    return Report(
        submission_id=submission_id,
        report_type=report_type,
        template_version=f"template-{report_type.value.lower()}-v1",
        artifact_ref=f"{submission_id}-{report_type.value.lower()}-{ref_suffix}",
        content=f"{report_type.value}-{ref_suffix}".encode(),
        generated_at=datetime(2026, 8, 18, 9, 20, 0),
    )


def _delivery(
    submission_id: str = "submission-1",
    report_type: ReportType = ReportType.CLIENT,
    attempt_number: int = 1,
) -> Delivery:
    recipient = "client@example.invalid" if report_type is ReportType.CLIENT else "internal@example.invalid"
    return Delivery(
        submission_id=submission_id,
        report_type=report_type,
        recipient=recipient,
        delivery_key=f"{submission_id}:{report_type.value}:{recipient}",
        attempt_number=attempt_number,
        status=DeliveryStatus.SENT,
        message_id=f"msg-{report_type.value.lower()}-{attempt_number}",
        attempted_at=datetime(2026, 8, 18, 9, 30, 0) + timedelta(minutes=attempt_number),
        sent_at=datetime(2026, 8, 18, 9, 31, 0) + timedelta(minutes=attempt_number),
    )


def _state(submission_id: str = "submission-1", status: SubmissionStatus = SubmissionStatus.RECEIVED) -> SubmissionState:
    return SubmissionState(
        submission_id=submission_id,
        status=status,
        attempt_counts={},
        updated_at=datetime(2026, 8, 18, 9, 40, 0),
    )


def _sqlalchemy_url(postgres_dsn: str) -> str:
    return postgres_dsn.replace("postgresql://", "postgresql+psycopg://", 1)


def _raw_insert_statement(submission: RawFormSubmission):
    return (
        pg_insert(RawFormSubmissionRow)
        .values(
            submission_id=submission.submission_id,
            form_id=submission.form_id,
            response_id=submission.response_id,
            received_at=submission.received_at,
            raw_payload=submission.raw_payload,
            form_schema_version_at_receipt=submission.form_schema_version_at_receipt,
        )
        .on_conflict_do_nothing()
    )


def _run_forced_duplicate_response_overlap(postgres_dsn: str, *, label: str, contender_callable):
    from src.persistence.postgres import PostgresRepositories

    sqlalchemy_url = _sqlalchemy_url(postgres_dsn)
    blocker_submission = _raw_submission(f"{label}-winner")
    contender_submission = replace(
        _raw_submission(f"{label}-loser"),
        response_id=blocker_submission.response_id,
    )
    blocker_engine = create_engine(sqlalchemy_url, future=True)
    contender_repositories = PostgresRepositories(sqlalchemy_url)
    contender_insert_started = Event()
    results: list[bool] = []
    errors: list[Exception] = []

    def before_cursor_execute(conn, cursor, statement, parameters, context, executemany) -> None:
        if "INSERT INTO raw_form_submissions" in statement:
            contender_insert_started.set()

    event.listen(contender_repositories._engine, "before_cursor_execute", before_cursor_execute)
    try:
        with blocker_engine.connect() as blocker_connection:
            blocker_transaction = blocker_connection.begin()
            blocker_connection.execute(_raw_insert_statement(blocker_submission))

            def run_contender() -> None:
                try:
                    results.append(contender_callable(contender_repositories, contender_submission))
                except Exception as exc:  # pragma: no cover - asserted below
                    errors.append(exc)

            contender_thread = Thread(target=run_contender)
            contender_thread.start()
            assert contender_insert_started.wait(timeout=5), "Contender insert never reached the database"
            blocker_transaction.commit()
            contender_thread.join(timeout=5)
            assert not contender_thread.is_alive(), "Contender thread remained blocked after blocker commit"

            persisted_count = blocker_connection.execute(
                select(func.count())
                .select_from(RawFormSubmissionRow)
                .where(
                    RawFormSubmissionRow.form_id == blocker_submission.form_id,
                    RawFormSubmissionRow.response_id == blocker_submission.response_id,
                )
            ).scalar_one()
    finally:
        event.remove(contender_repositories._engine, "before_cursor_execute", before_cursor_execute)
        contender_repositories.dispose()
        blocker_engine.dispose()

    return results, errors, persisted_count


def test_raw_form_submission_repository_contract(postgres_repositories) -> None:
    submission = _raw_submission()

    assert postgres_repositories.raw_submissions.insert(submission) is True
    assert postgres_repositories.raw_submissions.insert(submission) is False
    assert (
        postgres_repositories.raw_submissions.insert(
            replace(submission, submission_id="submission-1b")
        )
        is False
    )
    assert (
        postgres_repositories.raw_submissions.insert(
            replace(submission, response_id="response-submission-1b")
        )
        is False
    )
    assert postgres_repositories.raw_submissions.get(submission.submission_id) == submission
    assert (
        postgres_repositories.raw_submissions.find_by_response(submission.form_id, submission.response_id)
        == submission
    )
    assert postgres_repositories.raw_submissions.find_by_response("demo-form", "missing") is None


def test_raw_form_submission_insert_allows_only_one_real_database_winner_for_duplicate_response(postgres_dsn: str) -> None:
    results, errors, persisted_count = _run_forced_duplicate_response_overlap(
        postgres_dsn,
        label="current-insert",
        contender_callable=lambda repositories, submission: repositories.raw_submissions.insert(submission),
    )

    assert errors == []
    assert results == [False]
    assert persisted_count == 1


def test_old_insert_implementation_raises_under_forced_overlap(postgres_dsn: str) -> None:
    def old_insert_logic(repositories, submission: RawFormSubmission) -> bool:
        with repositories._session_factory.begin() as session:
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
            session.flush()
            return True

    results, errors, persisted_count = _run_forced_duplicate_response_overlap(
        postgres_dsn,
        label="old-insert",
        contender_callable=old_insert_logic,
    )

    assert results == []
    assert len(errors) == 1
    assert isinstance(errors[0], IntegrityError)
    assert persisted_count == 1


def test_raw_form_submission_insert_returns_false_for_duplicate_submission_id(postgres_repositories) -> None:
    submission = _raw_submission("duplicate-id")

    assert postgres_repositories.raw_submissions.insert(submission) is True
    assert (
        postgres_repositories.raw_submissions.insert(
            replace(submission, response_id="response-duplicate-id-2")
        )
        is False
    )


def test_normalized_application_repository_contract(postgres_repositories) -> None:
    submission = _raw_submission()
    postgres_repositories.raw_submissions.insert(submission)
    first = _normalized()
    second = replace(first, normalization_warnings=("retry-copy",))

    postgres_repositories.normalized_applications.insert(first)
    postgres_repositories.normalized_applications.insert(second)

    assert postgres_repositories.normalized_applications.get(submission.submission_id) == second
    assert postgres_repositories.normalized_applications.list_for_submission(submission.submission_id) == [
        first,
        second,
    ]


def test_assessment_repository_contract(postgres_repositories) -> None:
    submission = _raw_submission()
    postgres_repositories.raw_submissions.insert(submission)
    first = _assessment()
    second = replace(first, reasons=("Synthetic reason", "retry-copy"))

    postgres_repositories.assessments.insert(first)
    postgres_repositories.assessments.insert(second)

    assert postgres_repositories.assessments.get(submission.submission_id) == second
    assert postgres_repositories.assessments.list_for_submission(submission.submission_id) == [first, second]


def test_narrative_repository_contract(postgres_repositories) -> None:
    submission = _raw_submission()
    postgres_repositories.raw_submissions.insert(submission)
    first = _narrative(attempt_number=1, text="Narrative one")
    second = _narrative(attempt_number=2, text="Narrative two")

    postgres_repositories.narratives.insert(first)
    postgres_repositories.narratives.insert(second)

    assert postgres_repositories.narratives.get_latest(submission.submission_id) == second
    assert postgres_repositories.narratives.list_for_submission(submission.submission_id) == [first, second]


def test_report_repository_contract(postgres_repositories) -> None:
    submission = _raw_submission()
    postgres_repositories.raw_submissions.insert(submission)
    internal = _report(report_type=ReportType.INTERNAL, ref_suffix="internal-1")
    client_first = _report(report_type=ReportType.CLIENT, ref_suffix="client-1")
    client_second = _report(report_type=ReportType.CLIENT, ref_suffix="client-2")

    postgres_repositories.reports.insert(internal)
    postgres_repositories.reports.insert(client_first)
    postgres_repositories.reports.insert(client_second)

    assert postgres_repositories.reports.list_for_submission(submission.submission_id) == [
        internal,
        client_first,
        client_second,
    ]
    assert postgres_repositories.reports.get_by_type(submission.submission_id) == {
        ReportType.INTERNAL.value: internal,
        ReportType.CLIENT.value: client_second,
    }


def test_delivery_repository_contract(postgres_repositories) -> None:
    submission = _raw_submission()
    postgres_repositories.raw_submissions.insert(submission)
    first = _delivery(report_type=ReportType.INTERNAL, attempt_number=1)
    second = _delivery(report_type=ReportType.CLIENT, attempt_number=2)

    postgres_repositories.deliveries.insert(first)
    postgres_repositories.deliveries.insert(second)

    assert postgres_repositories.deliveries.list_for_submission(submission.submission_id) == [first, second]


def test_submission_state_repository_contract(postgres_repositories) -> None:
    submission = _raw_submission()
    postgres_repositories.raw_submissions.insert(submission)
    state = _state()
    postgres_repositories.submission_states.create(state)

    assert postgres_repositories.submission_states.get(submission.submission_id) == state

    updated_state = replace(
        state,
        status=SubmissionStatus.NORMALIZED,
        attempt_counts={PipelineStage.NORMALIZATION: 1},
        last_error=StageError(
            stage=PipelineStage.NORMALIZATION,
            reason_code="NONE",
            retryable=False,
            message="normalized",
            attempt_count=1,
            occurred_at=datetime(2026, 8, 18, 9, 41, 0),
        ),
        updated_at=datetime(2026, 8, 18, 9, 41, 0),
    )

    assert (
        postgres_repositories.submission_states.compare_and_set(
            submission.submission_id,
            expected_state=state,
            new_state=updated_state,
        )
        is True
    )
    assert postgres_repositories.submission_states.get(submission.submission_id) == updated_state
    assert (
        postgres_repositories.submission_states.compare_and_set(
            submission.submission_id,
            expected_state=state,
            new_state=replace(updated_state, status=SubmissionStatus.CLASSIFIED),
        )
        is False
    )


def test_compare_and_set_allows_only_one_real_database_claim(postgres_dsn: str) -> None:
    from src.persistence.postgres import PostgresRepositories

    seed = PostgresRepositories(postgres_dsn.replace("postgresql://", "postgresql+psycopg://", 1))
    submission = _raw_submission("race-submission")
    seed.raw_submissions.insert(submission)
    initial_state = _state("race-submission")
    seed.submission_states.create(initial_state)
    snapshot = seed.submission_states.get("race-submission")
    assert snapshot is not None
    seed.dispose()

    repositories = [
        PostgresRepositories(postgres_dsn.replace("postgresql://", "postgresql+psycopg://", 1))
        for _ in range(2)
    ]
    barrier = Barrier(2)
    results: list[bool] = []

    def attempt_claim(repo) -> None:
        candidate = replace(
            snapshot,
            attempt_counts={PipelineStage.NORMALIZATION: 1},
            updated_at=datetime(2026, 8, 18, 9, 45, 0),
        )
        barrier.wait()
        results.append(
            repo.submission_states.compare_and_set(
                "race-submission",
                expected_state=snapshot,
                new_state=candidate,
            )
        )

    threads = [Thread(target=attempt_claim, args=(repo,)) for repo in repositories]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    for repo in repositories:
        repo.dispose()

    assert results.count(True) == 1
    assert results.count(False) == 1


def test_append_only_tables_reject_update_and_delete(postgres_repositories, postgres_dsn: str) -> None:
    import psycopg

    submission = _raw_submission()
    postgres_repositories.raw_submissions.insert(submission)
    postgres_repositories.normalized_applications.insert(_normalized())
    postgres_repositories.assessments.insert(_assessment())
    postgres_repositories.narratives.insert(_narrative())
    postgres_repositories.reports.insert(_report(report_type=ReportType.INTERNAL, ref_suffix="internal"))
    postgres_repositories.deliveries.insert(_delivery(report_type=ReportType.INTERNAL, attempt_number=1))

    statements = {
        "raw_form_submissions": "UPDATE raw_form_submissions SET form_id = 'changed' WHERE submission_id = 'submission-1'",
        "normalized_applications": "DELETE FROM normalized_applications WHERE submission_id = 'submission-1'",
        "assessments": "UPDATE assessments SET qualification = 'STANDARD' WHERE submission_id = 'submission-1'",
        "narratives": "DELETE FROM narratives WHERE submission_id = 'submission-1'",
        "reports": "UPDATE reports SET artifact_ref = 'changed' WHERE submission_id = 'submission-1'",
        "deliveries": "DELETE FROM deliveries WHERE submission_id = 'submission-1'",
    }

    with psycopg.connect(postgres_dsn) as connection:
        with connection.cursor() as cursor:
            for table_name, statement in statements.items():
                with pytest.raises(psycopg.Error, match="append-only table"):
                    cursor.execute(statement)
                connection.rollback()

                cursor.execute("SELECT COUNT(*) FROM " + table_name)
                assert cursor.fetchone() == (1,), table_name
