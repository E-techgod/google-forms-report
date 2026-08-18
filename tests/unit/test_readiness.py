import pytest

from src.adapters.forms import SimpleFormPayloadParser
from src.api import WebhookReceiver
from src.config import (
    AlertChannel,
    AppConfig,
    ClientReportAllowlist,
    FormFieldMapping,
    FormSchemaMapping,
    LLMProviderConfig,
    PromptTemplate,
    ReadinessFailure,
    ReadinessGate,
    RecipientRouting,
    ReportTemplate,
    RetryPolicy,
    StartupReadinessError,
)
from src.domain.models import PipelineStage, ReportType, SubmissionStatus
from src.domain.rules import FieldEqualsRule, RuleSet
from src.persistence import InMemoryRepositories
from src.workflows import InMemoryTaskQueue


def _production_config() -> AppConfig:
    return AppConfig(
        env="production",
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
                fields=(FormFieldMapping("risk", "risk_flag", True),),
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
                max_attempts=5,
                backoff_seconds=(30, 120, 600, 1800, 7200),
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
    )


def test_readiness_gate_schema_check() -> None:
    config = _production_config()
    config.form_schema_mappings.clear()

    with pytest.raises(ReadinessFailure) as excinfo:
        ReadinessGate(config).ensure_stage_ready(PipelineStage.NORMALIZATION, form_id="form-1")

    assert excinfo.value.reason_code == "SCHEMA_NOT_CONFIGURED"


def test_readiness_gate_rules_check() -> None:
    config = _production_config()
    config.rule_sets.clear()

    with pytest.raises(ReadinessFailure) as excinfo:
        ReadinessGate(config).ensure_stage_ready(PipelineStage.CLASSIFICATION, form_id="form-1")

    assert excinfo.value.reason_code == "RULES_NOT_CONFIGURED"


def test_readiness_gate_llm_provider_check() -> None:
    config = _production_config()
    config.llm_provider_configs.clear()

    with pytest.raises(ReadinessFailure) as excinfo:
        ReadinessGate(config).ensure_stage_ready(PipelineStage.NARRATIVE, form_id="form-1")

    assert excinfo.value.reason_code == "LLM_PROVIDER_NOT_CONFIGURED"


def test_readiness_gate_prompt_template_check() -> None:
    config = _production_config()
    config.prompt_templates["prompt-v1"] = PromptTemplate(
        version="prompt-v1",
        approved_for_production=False,
        template_text="Draft prompt",
    )

    with pytest.raises(ReadinessFailure) as excinfo:
        ReadinessGate(config).ensure_stage_ready(PipelineStage.NARRATIVE, form_id="form-1")

    assert excinfo.value.reason_code == "DRAFT-UNAPPROVED"


def test_readiness_gate_report_template_check() -> None:
    config = _production_config()
    config.report_templates[(ReportType.CLIENT, "client-template-v1")] = ReportTemplate(
        version="client-template-v1",
        report_type=ReportType.CLIENT,
        approved_for_production=False,
        template_text="Draft client template",
    )

    with pytest.raises(ReadinessFailure) as excinfo:
        ReadinessGate(config).ensure_stage_ready(PipelineStage.REPORT, form_id="form-1")

    assert excinfo.value.reason_code == "DRAFT-UNAPPROVED"


def test_readiness_gate_recipient_routing_check() -> None:
    config = _production_config()
    config.recipient_routings.clear()

    with pytest.raises(ReadinessFailure) as excinfo:
        ReadinessGate(config).ensure_stage_ready(PipelineStage.DELIVERY, form_id="form-1")

    assert excinfo.value.reason_code == "RECIPIENTS_NOT_CONFIGURED"


def test_readiness_gate_allowlist_check() -> None:
    config = _production_config()
    config.client_report_allowlists["allowlist-v1"] = ClientReportAllowlist(
        version="allowlist-v1",
        approved_for_production=False,
        allowed_application_fields=(),
    )

    with pytest.raises(ReadinessFailure) as excinfo:
        ReadinessGate(config).ensure_stage_ready(PipelineStage.DELIVERY, form_id="form-1")

    assert excinfo.value.reason_code == "DRAFT-UNAPPROVED"


def test_readiness_gate_alert_channel_check() -> None:
    config = _production_config()
    config.alert_channels.clear()

    with pytest.raises(StartupReadinessError) as excinfo:
        ReadinessGate(config).validate_startup()

    assert excinfo.value.reason_code == "ALERT_CHANNEL_NOT_CONFIGURED"


def test_retention_policy_does_not_block_stage_execution() -> None:
    config = _production_config()

    ReadinessGate(config).ensure_stage_ready(PipelineStage.CLASSIFICATION, form_id="form-1")


def test_retry_policy_placeholder_does_not_block_stage_execution() -> None:
    config = _production_config()
    config.retry_policies.clear()

    ReadinessGate(config).ensure_stage_ready(PipelineStage.CLASSIFICATION, form_id="form-1")


def test_ingestion_is_not_blocked_by_missing_downstream_configs() -> None:
    repositories = InMemoryRepositories()
    queue = InMemoryTaskQueue()
    receiver = WebhookReceiver(
        parser=SimpleFormPayloadParser(),
        repositories=repositories,
        queue=queue,
    )

    response = receiver.handle(
        {
            "form_id": "form-1",
            "response_id": "response-1",
            "answers": {"risk": "yes"},
        }
    )

    assert response.status_code == 202
    assert response.submission_status == SubmissionStatus.RECEIVED
    assert repositories.raw_submissions.get(response.submission_id or "") is not None
