from __future__ import annotations

import logging
from dataclasses import replace
from datetime import datetime
from typing import Callable

from src.adapters.gmail.base import EmailSender, EmailSenderError
from src.adapters.llm.base import LLMProvider, LLMProviderError
from src.adapters.pdf.base import ReportRenderer, ReportRendererError
from src.config.models import AppConfig, PromptTemplate, ReportTemplate
from src.config.readiness import ReadinessFailure, ReadinessGate
from src.domain.contexts import (
    build_client_report_context,
    build_fallback_narrative,
    build_internal_report_context,
    build_narrative_context,
    should_use_fallback_narrative,
)
from src.domain.models import (
    Delivery,
    DeliveryStatus,
    Narrative,
    PipelineStage,
    RawFormSubmission,
    Report,
    ReportType,
    StageError,
    SubmissionState,
    SubmissionStatus,
)
from src.domain.normalization import NormalizationError, normalize_submission
from src.domain.rules import ClassificationFailure, RuleEngine
from src.domain.state_machine import (
    failure_status_for_stage,
    is_failure_status,
    is_terminal_status,
    is_valid_transition,
    stage_for_status,
)
from src.domain.validation import GenericNarrativeValidator, SemanticValidationFailure
from src.persistence.interfaces import RepositoryBundle

from .alerts import AlertEvent, AlertSink
from .queue import InMemoryTaskQueue

LOGGER = logging.getLogger(__name__)


class Worker:
    def __init__(
        self,
        *,
        repositories: RepositoryBundle,
        config: AppConfig,
        readiness_gate: ReadinessGate,
        queue: InMemoryTaskQueue,
        alert_sink: AlertSink,
        rule_engine: RuleEngine,
        llm_provider: LLMProvider,
        report_renderer: ReportRenderer,
        email_sender: EmailSender,
        narrative_validator: GenericNarrativeValidator,
        now_factory: Callable[[], datetime] | None = None,
    ) -> None:
        self._repositories = repositories
        self._config = config
        self._readiness_gate = readiness_gate
        self._queue = queue
        self._alert_sink = alert_sink
        self._rule_engine = rule_engine
        self._llm_provider = llm_provider
        self._report_renderer = report_renderer
        self._email_sender = email_sender
        self._narrative_validator = narrative_validator
        self._now_factory = now_factory or datetime.utcnow

    def process_next_task(self) -> bool:
        submission_id = self._queue.pop()
        if submission_id is None:
            return False
        self.process_submission(submission_id)
        return True

    def process_submission(self, submission_id: str, *, enqueue_follow_up: bool = True) -> SubmissionState:
        state = self._repositories.submission_states.get(submission_id)
        if state is None:
            raise KeyError(f"Unknown submission_id {submission_id}")
        if is_terminal_status(state.status):
            return state

        stage = stage_for_status(state.status)
        raw_submission = self._repositories.raw_submissions.get(submission_id)
        if raw_submission is None:
            raise KeyError(f"Missing raw submission {submission_id}")

        try:
            self._readiness_gate.ensure_stage_ready(stage, form_id=raw_submission.form_id)
            attempt = state.attempt_counts.get(stage, 0) + 1
            updated_state = replace(state, attempt_counts={**state.attempt_counts, stage: attempt})
            if not self._repositories.submission_states.compare_and_set(
                submission_id,
                expected_state=state,
                new_state=updated_state,
            ):
                return self._repositories.submission_states.get(submission_id)  # pragma: no cover
            state = updated_state
            new_status = self._execute_stage(stage, raw_submission, state)
            state = self._transition_to_status(state, new_status)
            if enqueue_follow_up and not is_terminal_status(state.status):
                self._queue.enqueue(submission_id)
            return state
        except ReadinessFailure as exc:
            return self._fail_stage(state, raw_submission, exc.stage, exc.reason_code, exc.message, False)
        except NormalizationError as exc:
            return self._fail_stage(state, raw_submission, stage, exc.reason_code, exc.message, False)
        except ClassificationFailure as exc:
            return self._fail_stage(state, raw_submission, stage, exc.reason_code, exc.message, False)
        except SemanticValidationFailure as exc:
            return self._fail_stage(state, raw_submission, stage, exc.reason_code, exc.message, False)
        except (LLMProviderError, ReportRendererError, EmailSenderError, ValueError) as exc:
            return self._handle_retryable_failure(state, raw_submission, stage, exc)

    def _execute_stage(
        self,
        stage: PipelineStage,
        raw_submission: RawFormSubmission,
        state: SubmissionState,
    ) -> SubmissionStatus:
        if stage == PipelineStage.NORMALIZATION:
            mapping_version = self._config.active_form_schema_versions.get(raw_submission.form_id)
            mapping = self._config.form_schema_mappings.get(mapping_version or "")
            if mapping is None:
                raise NormalizationError("SCHEMA_NOT_CONFIGURED", "No schema mapping registered")
            application = normalize_submission(raw_submission, mapping)
            self._repositories.normalized_applications.insert(application)
            return SubmissionStatus.NORMALIZED

        if stage == PipelineStage.CLASSIFICATION:
            application = self._repositories.normalized_applications.get(raw_submission.submission_id)
            if application is None:
                raise ValueError("Normalized application missing")
            assessment = self._rule_engine.classify(application, now=self._now_factory())
            self._repositories.assessments.insert(assessment)
            return SubmissionStatus.CLASSIFIED

        if stage == PipelineStage.NARRATIVE:
            application = self._repositories.normalized_applications.get(raw_submission.submission_id)
            assessment = self._repositories.assessments.get(raw_submission.submission_id)
            if application is None or assessment is None:
                raise ValueError("Narrative inputs missing")
            provider_config = self._config.llm_provider_configs.get(
                self._config.active_llm_provider_version or ""
            )
            if provider_config is None:
                raise LLMProviderError("LLM provider config missing")
            prompt_template = self._config.prompt_templates.get(provider_config.prompt_version)
            if prompt_template is None:
                raise ValueError("Prompt template missing")
            context = build_narrative_context(
                application,
                assessment,
                allowed_application_fields=self._config.narrative_allowed_fields,
            )
            attempt = state.attempt_counts[stage]
            if should_use_fallback_narrative(context, self._config.min_narrative_context_fields):
                narrative = build_fallback_narrative(
                    context,
                    prompt_version=prompt_template.version,
                    attempt_number=attempt,
                    now=self._now_factory(),
                )
            else:
                generation = self._llm_provider.generate_narrative(
                    context=context,
                    prompt_template=prompt_template,
                    provider_config=provider_config,
                )
                outcome = self._narrative_validator.validate(
                    text=generation.text,
                    context=context,
                    assessment=assessment,
                )
                if not outcome.ok:
                    raise SemanticValidationFailure(outcome.reason_code, outcome.message)
                narrative = Narrative(
                    submission_id=raw_submission.submission_id,
                    attempt_number=attempt,
                    provider=generation.provider,
                    model=generation.model,
                    prompt_version=prompt_template.version,
                    raw_output=generation.raw_output,
                    validation_result=outcome.reason_code,
                    text=generation.text,
                    generated_at=self._now_factory(),
                )
            self._repositories.narratives.insert(narrative)
            return SubmissionStatus.NARRATIVE_READY

        if stage == PipelineStage.REPORT:
            application = self._repositories.normalized_applications.get(raw_submission.submission_id)
            assessment = self._repositories.assessments.get(raw_submission.submission_id)
            narrative = self._repositories.narratives.get_latest(raw_submission.submission_id)
            if application is None or assessment is None or narrative is None:
                raise ValueError("Report inputs missing")
            contexts = {
                ReportType.INTERNAL: build_internal_report_context(application, assessment, narrative),
                ReportType.CLIENT: build_client_report_context(
                    application,
                    narrative,
                    assessment,
                    allowed_application_fields=self._current_allowlist().allowed_application_fields,
                ),
            }
            for report_type, context in contexts.items():
                template = self._get_report_template(report_type)
                rendered = self._report_renderer.render(context=context, template=template)
                self._repositories.reports.insert(
                    Report(
                        submission_id=raw_submission.submission_id,
                        report_type=report_type,
                        template_version=template.version,
                        artifact_ref=rendered.artifact_ref,
                        content=rendered.content,
                        generated_at=self._now_factory(),
                    )
                )
            return SubmissionStatus.REPORTS_READY

        reports = self._repositories.reports.get_by_type(raw_submission.submission_id)
        if ReportType.INTERNAL.value not in reports or ReportType.CLIENT.value not in reports:
            raise ValueError("Expected reports missing")
        routing = self._current_routing()
        application = self._repositories.normalized_applications.get(raw_submission.submission_id)
        if application is None:
            raise ValueError("Normalized application missing")
        recipients: list[tuple[ReportType, str]] = []
        recipients.extend((ReportType.INTERNAL, value) for value in routing.internal_report_recipients)
        if routing.client_email_field:
            client_email = application.fields.get(routing.client_email_field)
            if isinstance(client_email, str) and client_email:
                recipients.append((ReportType.CLIENT, client_email))
        if not recipients:
            raise EmailSenderError("RECIPIENTS_NOT_CONFIGURED")

        for report_type, recipient in recipients:
            delivery_key = f"{raw_submission.submission_id}:{report_type.value}:{recipient}"
            prior_deliveries = [
                delivery
                for delivery in self._repositories.deliveries.list_for_submission(raw_submission.submission_id)
                if delivery.delivery_key == delivery_key
            ]
            if any(delivery.status == DeliveryStatus.SENT for delivery in prior_deliveries):
                continue
            existing = self._email_sender.find_existing(delivery_key)
            report = reports[report_type.value]
            if existing is None:
                receipt = self._email_sender.send(
                    report=report,
                    recipient=recipient,
                    delivery_key=delivery_key,
                )
            else:
                receipt = existing
            attempt_number = len(prior_deliveries) + 1
            self._repositories.deliveries.insert(
                Delivery(
                    submission_id=raw_submission.submission_id,
                    report_type=report_type,
                    recipient=recipient,
                    delivery_key=delivery_key,
                    attempt_number=attempt_number,
                    status=DeliveryStatus.SENT,
                    message_id=receipt.message_id,
                    attempted_at=self._now_factory(),
                    sent_at=receipt.sent_at,
                )
            )
        return SubmissionStatus.COMPLETED

    def _current_allowlist(self):
        return self._config.client_report_allowlists[
            self._config.active_client_allowlist_version or ""
        ]

    def _current_routing(self):
        return self._config.recipient_routings[self._config.active_recipient_routing_version or ""]

    def _get_report_template(self, report_type: ReportType) -> ReportTemplate:
        version = self._config.active_report_template_versions[report_type]
        return self._config.report_templates[(report_type, version)]

    def _transition_to_status(
        self,
        state: SubmissionState,
        new_status: SubmissionStatus,
    ) -> SubmissionState:
        deliveries_complete = self._deliveries_complete(state.submission_id, new_status)
        if not is_valid_transition(
            state.status,
            new_status,
            deliveries_complete=deliveries_complete,
        ):
            raise ValueError(f"Invalid state transition {state.status} -> {new_status}")
        updated_state = replace(state, status=new_status, last_error=None, updated_at=self._now_factory())
        if not self._repositories.submission_states.compare_and_set(
            state.submission_id,
            expected_state=state,
            new_state=updated_state,
        ):
            raise ValueError("State transition lost compare-and-set")
        LOGGER.info("stage_transition submission_id=%s status=%s", state.submission_id, new_status.value)
        return updated_state

    def _deliveries_complete(
        self,
        submission_id: str,
        new_status: SubmissionStatus,
    ) -> bool:
        if new_status != SubmissionStatus.COMPLETED:
            return False

        reports = self._repositories.reports.get_by_type(submission_id)
        if ReportType.INTERNAL.value not in reports or ReportType.CLIENT.value not in reports:
            return False

        application = self._repositories.normalized_applications.get(submission_id)
        if application is None:
            return False

        routing = self._current_routing()
        required_recipients: list[tuple[ReportType, str]] = [
            (ReportType.INTERNAL, recipient) for recipient in routing.internal_report_recipients
        ]
        if routing.client_email_field:
            client_email = application.fields.get(routing.client_email_field)
            if isinstance(client_email, str) and client_email:
                required_recipients.append((ReportType.CLIENT, client_email))

        delivery_rows = self._repositories.deliveries.list_for_submission(submission_id)
        sent_delivery_keys = {
            delivery.delivery_key for delivery in delivery_rows if delivery.status == DeliveryStatus.SENT
        }
        required_delivery_keys = {
            f"{submission_id}:{report_type.value}:{recipient}"
            for report_type, recipient in required_recipients
        }
        return bool(required_delivery_keys) and sent_delivery_keys.issuperset(required_delivery_keys)

    def _handle_retryable_failure(
        self,
        state: SubmissionState,
        raw_submission: RawFormSubmission,
        stage: PipelineStage,
        error: Exception,
    ) -> SubmissionState:
        policy = self._config.retry_policies.get(self._config.active_retry_policy_version or "")
        max_attempts = policy.max_attempts if policy else 5
        attempt = state.attempt_counts.get(stage, 0)
        if is_failure_status(state.status) and attempt >= max_attempts:
            return self._fail_permanently(state, stage, str(error))
        failed_state = self._fail_stage(state, raw_submission, stage, type(error).__name__, str(error), True)
        self._queue.enqueue(raw_submission.submission_id)
        return failed_state

    def _fail_stage(
        self,
        state: SubmissionState,
        raw_submission: RawFormSubmission,
        stage: PipelineStage,
        reason_code: str,
        message: str,
        retryable: bool,
    ) -> SubmissionState:
        new_status = failure_status_for_stage(stage)
        error = StageError(
            stage=stage,
            reason_code=reason_code,
            retryable=retryable,
            message=message,
            attempt_count=state.attempt_counts.get(stage, 0),
            occurred_at=self._now_factory(),
        )
        updated_state = replace(state, status=new_status, last_error=error, updated_at=self._now_factory())
        if not is_valid_transition(state.status, new_status):
            raise ValueError(f"Invalid state transition {state.status} -> {new_status}")
        if not self._repositories.submission_states.compare_and_set(
            state.submission_id,
            expected_state=state,
            new_state=updated_state,
        ):
            raise ValueError("Failure transition lost compare-and-set")
        self._alert_sink.send(
            AlertEvent(
                submission_id=raw_submission.submission_id,
                stage=stage,
                reason_code=reason_code,
                message=message,
                emitted_at=self._now_factory(),
            )
        )
        return updated_state

    def _fail_permanently(
        self,
        state: SubmissionState,
        stage: PipelineStage,
        message: str,
    ) -> SubmissionState:
        if not is_failure_status(state.status):
            raise ValueError("FAILED_PERMANENT may only follow a stage failure")
        error = StageError(
            stage=stage,
            reason_code="FAILED_PERMANENT",
            retryable=False,
            message=message,
            attempt_count=state.attempt_counts.get(stage, 0),
            occurred_at=self._now_factory(),
        )
        updated_state = replace(
            state,
            status=SubmissionStatus.FAILED_PERMANENT,
            last_error=error,
            updated_at=self._now_factory(),
        )
        if not self._repositories.submission_states.compare_and_set(
            state.submission_id,
            expected_state=state,
            new_state=updated_state,
        ):
            raise ValueError("Permanent failure transition lost compare-and-set")
        return updated_state
