from __future__ import annotations

import logging
from dataclasses import replace
from datetime import datetime
from threading import Barrier, Thread

import pytest

from src.adapters.forms import SimpleFormPayloadParser
from src.adapters.gmail import EmailSenderError, FakeEmailSender
from src.adapters.llm import LLMGeneration, LLMProviderError, NullLLMProvider
from src.adapters.pdf import FakeReportRenderer, ReportRendererError
from src.api import WebhookReceiver
from src.config import (
    AlertChannel,
    AppConfig,
    ClientReportAllowlist,
    FormFieldMapping,
    FormSchemaMapping,
    LLMProviderConfig,
    PromptTemplate,
    ReadinessGate,
    RecipientRouting,
    ReportTemplate,
    RetryPolicy,
)
from src.domain import (
    FieldEqualsRule,
    GenericNarrativeValidator,
    PipelineStage,
    ReportType,
    RuleSet,
    StaticRuleEngine,
    SubmissionState,
    SubmissionStatus,
)
from src.persistence import InMemoryRepositories
from src.workflows import InMemoryAlertSink, InMemoryTaskQueue, Worker


class ConditionalEmailSender(FakeEmailSender):
    def __init__(self, *, failing_recipient: str) -> None:
        super().__init__(now_factory=lambda: datetime(2026, 8, 18))
        self._failing_recipient = failing_recipient
        self._failed_once = False

    def send(self, *, report, recipient: str, delivery_key: str):
        if recipient == self._failing_recipient and not self._failed_once:
            self._failed_once = True
            raise EmailSenderError("Simulated transient email failure")
        return super().send(report=report, recipient=recipient, delivery_key=delivery_key)


class MismatchLLMProvider(NullLLMProvider):
    def generate_narrative(self, *, context, prompt_template, provider_config):
        self.calls += 1
        return LLMGeneration(
            text="This narrative omits the deterministic label.",
            raw_output="This narrative omits the deterministic label.",
            provider=provider_config.provider_name,
            model=provider_config.model_name,
        )


def _build_app(
    *,
    env: str = "development",
    min_narrative_context_fields: int = 0,
    email_sender: FakeEmailSender | None = None,
    llm_provider: NullLLMProvider | None = None,
    report_renderer: FakeReportRenderer | None = None,
    validator: GenericNarrativeValidator | None = None,
) -> tuple[WebhookReceiver, Worker, InMemoryRepositories, InMemoryTaskQueue, AppConfig]:
    repositories = InMemoryRepositories()
    queue = InMemoryTaskQueue()
    config = AppConfig(
        env=env,
        active_rule_set_version="rules-v1",
        active_llm_provider_version="llm-v1",
        active_client_allowlist_version="allowlist-v1",
        active_recipient_routing_version="routing-v1",
        active_alert_channel_version="alert-v1",
        active_retry_policy_version="retry-v1",
        active_form_schema_versions={"form-1": "schema-v1"},
        active_report_template_versions={
            ReportType.INTERNAL: "internal-template-v1",
            ReportType.CLIENT: "client-template-v1",
        },
        rule_sets={
            "rules-v1": RuleSet(
                version="rules-v1",
                approved_for_production=True,
                rules=(
                    FieldEqualsRule(
                        code="FLAG-1",
                        field_name="risk_flag",
                        expected_value="yes",
                        reason="Synthetic reason",
                    ),
                ),
                qualification_if_any_triggered="REVIEW",
                qualification_if_none_triggered="STANDARD",
            )
        },
        form_schema_mappings={
            "schema-v1": FormSchemaMapping(
                version="schema-v1",
                form_id="form-1",
                approved_for_production=True,
                fields=(
                    FormFieldMapping("name", "applicant_name", True),
                    FormFieldMapping("email", "client_email", True),
                    FormFieldMapping("risk", "risk_flag", True),
                ),
            )
        },
        client_report_allowlists={
            "allowlist-v1": ClientReportAllowlist(
                version="allowlist-v1",
                approved_for_production=True,
                allowed_application_fields=(),
            )
        },
        recipient_routings={
            "routing-v1": RecipientRouting(
                version="routing-v1",
                approved_for_production=True,
                internal_report_recipients=("internal@example.invalid",),
                client_email_field="client_email",
            )
        },
        prompt_templates={
            "prompt-v1": PromptTemplate(
                version="prompt-v1",
                approved_for_production=True,
                template_text="Approved prompt",
            )
        },
        report_templates={
            (ReportType.INTERNAL, "internal-template-v1"): ReportTemplate(
                version="internal-template-v1",
                report_type=ReportType.INTERNAL,
                approved_for_production=True,
                template_text="Approved internal template",
            ),
            (ReportType.CLIENT, "client-template-v1"): ReportTemplate(
                version="client-template-v1",
                report_type=ReportType.CLIENT,
                approved_for_production=True,
                template_text="Approved client template",
            ),
        },
        alert_channels={
            "alert-v1": AlertChannel(
                version="alert-v1",
                approved_for_production=True,
                destination="ops@example.invalid",
            )
        },
        retry_policies={
            "retry-v1": RetryPolicy(
                version="retry-v1",
                approved_for_production=True,
                max_attempts=2,
                backoff_seconds=(30, 120),
            )
        },
        llm_provider_configs={
            "llm-v1": LLMProviderConfig(
                version="llm-v1",
                provider_name="null-llm",
                model_name="template-only",
                prompt_version="prompt-v1",
                approved_for_production=True,
            )
        },
        narrative_allowed_fields=("applicant_name",),
        min_narrative_context_fields=min_narrative_context_fields,
    )
    worker = Worker(
        repositories=repositories,
        config=config,
        readiness_gate=ReadinessGate(config),
        queue=queue,
        alert_sink=InMemoryAlertSink(),
        rule_engine=StaticRuleEngine(config.rule_sets, config.active_rule_set_version),
        llm_provider=llm_provider or NullLLMProvider(),
        report_renderer=report_renderer or FakeReportRenderer(),
        email_sender=email_sender or FakeEmailSender(now_factory=lambda: datetime(2026, 8, 18)),
        narrative_validator=validator or GenericNarrativeValidator(),
        now_factory=lambda: datetime(2026, 8, 18),
    )
    receiver = WebhookReceiver(
        parser=SimpleFormPayloadParser(),
        repositories=repositories,
        queue=queue,
        now_factory=lambda: datetime(2026, 8, 18),
    )
    return receiver, worker, repositories, queue, config


def _submit_payload(receiver: WebhookReceiver, *, response_id: str = "response-1", include_email: bool = True):
    answers = {"name": "test-applicant-001", "risk": "yes"}
    if include_email:
        answers["email"] = "test-applicant-001@example.invalid"
    return receiver.handle(
        {
            "form_id": "form-1",
            "response_id": response_id,
            "form_schema_version": "schema-v1",
            "answers": answers,
        }
    )


def _drain(worker: Worker) -> None:
    while worker.process_next_task():
        pass


def test_full_lifecycle_preserves_every_stage_output(caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.INFO)
    receiver, worker, repositories, _, _ = _build_app()

    response = _submit_payload(receiver)
    _drain(worker)

    submission_id = response.submission_id or ""
    state = repositories.submission_states.get(submission_id)
    assert state is not None
    assert state.status == SubmissionStatus.COMPLETED
    assert repositories.raw_submissions.get(submission_id) is not None
    assert repositories.normalized_applications.get(submission_id) is not None
    assessment = repositories.assessments.get(submission_id)
    assert assessment is not None and assessment.rule_version == "rules-v1"
    narrative = repositories.narratives.get_latest(submission_id)
    assert narrative is not None and narrative.prompt_version == "prompt-v1"
    reports = repositories.reports.list_for_submission(submission_id)
    assert {report.template_version for report in reports} == {
        "internal-template-v1",
        "client-template-v1",
    }
    deliveries = repositories.deliveries.list_for_submission(submission_id)
    assert len(deliveries) == 2
    assert "test-applicant-001" not in caplog.text
    assert "test-applicant-001@example.invalid" not in caplog.text
    assert "yes" not in caplog.text


def test_duplicate_submission_is_rejected_without_rerunning_pipeline() -> None:
    receiver, worker, repositories, _, _ = _build_app()

    first = _submit_payload(receiver, response_id="duplicate-response")
    _drain(worker)
    second = _submit_payload(receiver, response_id="duplicate-response")

    assert first.submission_status == SubmissionStatus.RECEIVED
    assert second.submission_status == SubmissionStatus.REJECTED_DUPLICATE
    assert len(repositories.deliveries.list_for_submission(first.submission_id or "")) == 2


def test_crash_and_resume_continues_from_persisted_state() -> None:
    receiver, worker, repositories, queue, _ = _build_app()

    response = _submit_payload(receiver, response_id="resume-response")
    submission_id = response.submission_id or ""
    assert queue.pop() == submission_id
    worker.process_submission(submission_id, enqueue_follow_up=False)
    assert repositories.submission_states.get(submission_id).status == SubmissionStatus.NORMALIZED
    assert len(queue) == 0

    queue.enqueue(submission_id)
    _drain(worker)

    assert repositories.submission_states.get(submission_id).status == SubmissionStatus.COMPLETED
    assert len(repositories.narratives.list_for_submission(submission_id)) == 1


def test_missing_required_data_fails_normalization_without_downstream_side_effects() -> None:
    receiver, worker, repositories, _, _ = _build_app()

    response = receiver.handle(
        {
            "form_id": "form-1",
            "response_id": "missing-required-1",
            "form_schema_version": "schema-v1",
            "answers": {"risk": "yes"},
        }
    )
    _drain(worker)

    submission_id = response.submission_id or ""
    state = repositories.submission_states.get(submission_id)
    assert state.status == SubmissionStatus.NORMALIZATION_FAILED
    assert repositories.normalized_applications.get(submission_id) is None


def test_schema_not_configured_fails_closed_but_keeps_raw_submission() -> None:
    receiver, worker, repositories, _, config = _build_app()
    config.form_schema_mappings.clear()

    response = _submit_payload(receiver, response_id="schema-missing-1")
    _drain(worker)

    submission_id = response.submission_id or ""
    assert repositories.raw_submissions.get(submission_id) is not None
    assert repositories.submission_states.get(submission_id).status == SubmissionStatus.NORMALIZATION_FAILED
    assert repositories.submission_states.get(submission_id).last_error.reason_code == "SCHEMA_NOT_CONFIGURED"


def test_llm_timeout_retries_and_then_completes() -> None:
    llm_provider = NullLLMProvider()
    llm_provider.fail_next_call(LLMProviderError("timeout"))
    receiver, worker, repositories, _, _ = _build_app(llm_provider=llm_provider)

    response = _submit_payload(receiver, response_id="llm-timeout-1")
    _drain(worker)

    state = repositories.submission_states.get(response.submission_id or "")
    assert state.status == SubmissionStatus.COMPLETED
    assert state.attempt_counts  # narrative retried through persisted state


def test_narrative_validation_failure_is_not_retried_and_preserves_reason_code() -> None:
    llm_provider = MismatchLLMProvider()
    receiver, worker, repositories, _, _ = _build_app(llm_provider=llm_provider)

    response = _submit_payload(receiver, response_id="narrative-invalid-1")
    _drain(worker)

    state = repositories.submission_states.get(response.submission_id or "")
    assert state.status == SubmissionStatus.NARRATIVE_FAILED
    assert state.last_error is not None
    assert state.last_error.reason_code == "QUALIFICATION_MISMATCH"
    assert state.last_error.retryable is False
    assert llm_provider.calls == 1


def test_report_render_failure_retries_and_then_completes() -> None:
    renderer = FakeReportRenderer()
    renderer.fail_next_call(ReportRendererError("render failed"))
    receiver, worker, repositories, _, _ = _build_app(report_renderer=renderer)

    response = _submit_payload(receiver, response_id="render-failure-1")
    _drain(worker)

    assert repositories.submission_states.get(response.submission_id or "").status == SubmissionStatus.COMPLETED


def test_partial_delivery_retries_only_failed_recipient() -> None:
    sender = ConditionalEmailSender(failing_recipient="test-applicant-001@example.invalid")
    receiver, worker, repositories, _, _ = _build_app(email_sender=sender)

    response = _submit_payload(receiver, response_id="partial-delivery-1")
    _drain(worker)

    submission_id = response.submission_id or ""
    state = repositories.submission_states.get(submission_id)
    assert state.status == SubmissionStatus.COMPLETED
    assert state.attempt_counts[PipelineStage.DELIVERY] == 2
    deliveries = repositories.deliveries.list_for_submission(submission_id)
    assert len(deliveries) == 2
    internal_deliveries = [delivery for delivery in deliveries if delivery.report_type == ReportType.INTERNAL]
    client_deliveries = [delivery for delivery in deliveries if delivery.report_type == ReportType.CLIENT]
    assert len(internal_deliveries) == 1
    assert len(client_deliveries) == 1
    assert sender.calls == 2


def test_queue_redelivery_after_completion_is_a_no_op() -> None:
    receiver, worker, repositories, queue, _ = _build_app()

    response = _submit_payload(receiver, response_id="queue-retry-1")
    _drain(worker)
    queue.enqueue(response.submission_id or "")
    _drain(worker)


def test_completed_transition_is_rejected_until_all_deliveries_exist() -> None:
    receiver, worker, repositories, _, _ = _build_app()

    response = _submit_payload(receiver, response_id="completed-guard-1")
    submission_id = response.submission_id or ""
    assert repositories.submission_states.get(submission_id) is not None

    worker.process_submission(submission_id, enqueue_follow_up=False)
    worker.process_submission(submission_id, enqueue_follow_up=False)
    worker.process_submission(submission_id, enqueue_follow_up=False)
    worker.process_submission(submission_id, enqueue_follow_up=False)

    state = repositories.submission_states.get(submission_id)
    assert state is not None
    assert state.status == SubmissionStatus.REPORTS_READY

    with pytest.raises(ValueError, match="Invalid state transition"):
        worker._transition_to_status(state, SubmissionStatus.COMPLETED)


def test_submission_state_compare_and_set_allows_only_one_racing_claim() -> None:
    repositories = InMemoryRepositories()
    initial_state = SubmissionState(
        submission_id="submission-1",
        status=SubmissionStatus.RECEIVED,
        attempt_counts={},
        updated_at=datetime(2026, 8, 18),
    )
    repositories.submission_states.create(initial_state)

    snapshot = repositories.submission_states.get("submission-1")
    barrier = Barrier(2)
    results: list[bool] = []

    def attempt_claim() -> None:
        assert snapshot is not None
        candidate = replace(
            snapshot,
            attempt_counts={**snapshot.attempt_counts, PipelineStage.NORMALIZATION: 1},
        )
        barrier.wait()
        results.append(
            repositories.submission_states.compare_and_set(
                "submission-1",
                expected_state=snapshot,
                new_state=candidate,
            )
        )

    threads = [Thread(target=attempt_claim) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert results.count(True) == 1
    assert results.count(False) == 1
    claimed_state = repositories.submission_states.get("submission-1")
    assert claimed_state is not None
    assert claimed_state.attempt_counts == {PipelineStage.NORMALIZATION: 1}


def test_normalized_and_assessment_repositories_are_append_only() -> None:
    receiver, worker, repositories, _, _ = _build_app()

    response = _submit_payload(receiver, response_id="append-only-1")
    submission_id = response.submission_id or ""
    worker.process_submission(submission_id, enqueue_follow_up=False)
    worker.process_submission(submission_id, enqueue_follow_up=False)

    application = repositories.normalized_applications.get(submission_id)
    assessment = repositories.assessments.get(submission_id)
    assert application is not None
    assert assessment is not None

    repositories.normalized_applications.insert(replace(application, normalization_warnings=("retry-copy",)))
    repositories.assessments.insert(replace(assessment, reasons=("Synthetic reason", "retry-copy")))

    applications = repositories.normalized_applications.list_for_submission(submission_id)
    assessments = repositories.assessments.list_for_submission(submission_id)
    assert len(applications) == 2
    assert len(assessments) == 2
    assert applications[0].normalization_warnings == ()
    assert applications[-1].normalization_warnings == ("retry-copy",)
    assert assessments[0].reasons == ("Synthetic reason",)
    assert assessments[-1].reasons == ("Synthetic reason", "retry-copy")


def test_min_context_floor_uses_deterministic_fallback() -> None:
    receiver, worker, repositories, _, _ = _build_app(min_narrative_context_fields=2)

    response = _submit_payload(receiver, response_id="fallback-narrative-1")
    _drain(worker)

    narrative = repositories.narratives.get_latest(response.submission_id or "")
    assert narrative.used_fallback is True
