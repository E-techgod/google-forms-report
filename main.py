from __future__ import annotations

import logging
from datetime import datetime

from src.adapters.forms import SimpleFormPayloadParser
from src.adapters.gmail import FakeEmailSender
from src.adapters.llm import NullLLMProvider
from src.adapters.pdf import FakeReportRenderer
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
from src.domain import FieldEqualsRule, GenericNarrativeValidator, ReportType, RuleSet, StaticRuleEngine
from src.persistence import InMemoryRepositories
from src.workflows import InMemoryAlertSink, InMemoryTaskQueue, Worker


def build_demo_components() -> tuple[WebhookReceiver, Worker, InMemoryRepositories]:
    now_factory = datetime.utcnow
    repositories = InMemoryRepositories()
    queue = InMemoryTaskQueue()
    config = AppConfig(
        env="development",
        active_rule_set_version="synthetic-v1",
        active_llm_provider_version="synthetic-llm-v1",
        active_client_allowlist_version="synthetic-allowlist-v1",
        active_recipient_routing_version="synthetic-routing-v1",
        active_alert_channel_version="synthetic-alert-v1",
        active_retry_policy_version="synthetic-retry-v1",
        active_form_schema_versions={"demo-form": "synthetic-schema-v1"},
        active_report_template_versions={
            ReportType.INTERNAL: "synthetic-internal-template-v1",
            ReportType.CLIENT: "synthetic-client-template-v1",
        },
        narrative_allowed_fields=("applicant_name",),
        rule_sets={
            "synthetic-v1": RuleSet(
                version="synthetic-v1",
                approved_for_production=False,
                rules=(
                    FieldEqualsRule(
                        code="SYNTHETIC-FLAG",
                        field_name="risk_flag",
                        expected_value="yes",
                        reason="Synthetic deterministic flag",
                    ),
                ),
                qualification_if_any_triggered="REVIEW",
                qualification_if_none_triggered="STANDARD",
            )
        },
        form_schema_mappings={
            "synthetic-schema-v1": FormSchemaMapping(
                version="synthetic-schema-v1",
                form_id="demo-form",
                approved_for_production=False,
                fields=(
                    FormFieldMapping("name", "applicant_name", True),
                    FormFieldMapping("email", "client_email", True),
                    FormFieldMapping("risk", "risk_flag", True),
                ),
            )
        },
        client_report_allowlists={
            "synthetic-allowlist-v1": ClientReportAllowlist(
                version="synthetic-allowlist-v1",
                approved_for_production=False,
                allowed_application_fields=(),
            )
        },
        recipient_routings={
            "synthetic-routing-v1": RecipientRouting(
                version="synthetic-routing-v1",
                approved_for_production=False,
                internal_report_recipients=("internal@example.invalid",),
                client_email_field="client_email",
            )
        },
        prompt_templates={
            "synthetic-prompt-v1": PromptTemplate(
                version="synthetic-prompt-v1",
                approved_for_production=False,
                template_text="DRAFT-UNAPPROVED synthetic prompt.",
            )
        },
        report_templates={
            (ReportType.INTERNAL, "synthetic-internal-template-v1"): ReportTemplate(
                version="synthetic-internal-template-v1",
                report_type=ReportType.INTERNAL,
                approved_for_production=False,
                template_text="DRAFT-UNAPPROVED internal template.",
            ),
            (ReportType.CLIENT, "synthetic-client-template-v1"): ReportTemplate(
                version="synthetic-client-template-v1",
                report_type=ReportType.CLIENT,
                approved_for_production=False,
                template_text="DRAFT-UNAPPROVED client template.",
            ),
        },
        alert_channels={
            "synthetic-alert-v1": AlertChannel(
                version="synthetic-alert-v1",
                approved_for_production=False,
                destination="log-only",
            )
        },
        retry_policies={
            "synthetic-retry-v1": RetryPolicy(
                version="synthetic-retry-v1",
                approved_for_production=False,
                max_attempts=5,
                backoff_seconds=(30, 120, 600, 1800, 7200),
            )
        },
        llm_provider_configs={
            "synthetic-llm-v1": LLMProviderConfig(
                version="synthetic-llm-v1",
                provider_name="null-llm",
                model_name="template-only",
                prompt_version="synthetic-prompt-v1",
                approved_for_production=False,
            )
        },
    )
    readiness_gate = ReadinessGate(config)
    readiness_gate.validate_startup()
    rule_engine = StaticRuleEngine(config.rule_sets, config.active_rule_set_version)
    worker = Worker(
        repositories=repositories,
        config=config,
        readiness_gate=readiness_gate,
        queue=queue,
        alert_sink=InMemoryAlertSink(),
        rule_engine=rule_engine,
        llm_provider=NullLLMProvider(),
        report_renderer=FakeReportRenderer(),
        email_sender=FakeEmailSender(),
        narrative_validator=GenericNarrativeValidator(),
        now_factory=now_factory,
    )
    receiver = WebhookReceiver(
        parser=SimpleFormPayloadParser(),
        repositories=repositories,
        queue=queue,
        now_factory=now_factory,
    )
    return receiver, worker, repositories


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    receiver, worker, repositories = build_demo_components()
    response = receiver.handle(
        {
            "form_id": "demo-form",
            "response_id": "demo-response-001",
            "form_schema_version": "synthetic-schema-v1",
            "answers": {
                "name": "test-applicant-001",
                "email": "test-applicant-001@example.invalid",
                "risk": "yes",
            },
        }
    )
    while worker.process_next_task():
        pass
    state = repositories.submission_states.get(response.submission_id or "")
    print(f"submission_id={response.submission_id} status={state.status if state else 'missing'}")


if __name__ == "__main__":
    main()
