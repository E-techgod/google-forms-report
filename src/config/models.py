from __future__ import annotations

from dataclasses import dataclass, field

from src.domain.models import ReportType
from src.domain.rules import RuleSet


@dataclass(frozen=True)
class FormFieldMapping:
    source_key: str
    target_key: str
    required: bool
    transform: str = "identity"


@dataclass(frozen=True)
class FormSchemaMapping:
    version: str
    form_id: str
    approved_for_production: bool
    fields: tuple[FormFieldMapping, ...]


@dataclass(frozen=True)
class ClientReportAllowlist:
    version: str
    approved_for_production: bool
    allowed_application_fields: tuple[str, ...] = ()


@dataclass(frozen=True)
class RecipientRouting:
    version: str
    approved_for_production: bool
    internal_report_recipients: tuple[str, ...]
    client_email_field: str | None


@dataclass(frozen=True)
class PromptTemplate:
    version: str
    approved_for_production: bool
    template_text: str


@dataclass(frozen=True)
class ReportTemplate:
    version: str
    report_type: ReportType
    approved_for_production: bool
    template_text: str


@dataclass(frozen=True)
class AlertChannel:
    version: str
    approved_for_production: bool
    destination: str


@dataclass(frozen=True)
class RetentionPolicy:
    version: str
    approved_for_production: bool
    per_entity_days: dict[str, int]


@dataclass(frozen=True)
class RetryPolicy:
    version: str
    approved_for_production: bool
    max_attempts: int
    backoff_seconds: tuple[int, ...]
    gmail_rate_limit_backoff_seconds: tuple[int, ...] = (300, 900, 3600)


@dataclass(frozen=True)
class LLMProviderConfig:
    version: str
    provider_name: str
    model_name: str
    prompt_version: str
    approved_for_production: bool
    secret_ref: str | None = None


@dataclass
class AppConfig:
    env: str = "development"
    active_rule_set_version: str | None = None
    active_llm_provider_version: str | None = None
    active_client_allowlist_version: str | None = None
    active_recipient_routing_version: str | None = None
    active_alert_channel_version: str | None = None
    active_retry_policy_version: str | None = None
    active_form_schema_versions: dict[str, str] = field(default_factory=dict)
    active_report_template_versions: dict[ReportType, str] = field(default_factory=dict)
    rule_sets: dict[str, RuleSet] = field(default_factory=dict)
    form_schema_mappings: dict[str, FormSchemaMapping] = field(default_factory=dict)
    client_report_allowlists: dict[str, ClientReportAllowlist] = field(default_factory=dict)
    recipient_routings: dict[str, RecipientRouting] = field(default_factory=dict)
    prompt_templates: dict[str, PromptTemplate] = field(default_factory=dict)
    report_templates: dict[tuple[ReportType, str], ReportTemplate] = field(default_factory=dict)
    alert_channels: dict[str, AlertChannel] = field(default_factory=dict)
    retention_policies: dict[str, RetentionPolicy] = field(default_factory=dict)
    retry_policies: dict[str, RetryPolicy] = field(default_factory=dict)
    llm_provider_configs: dict[str, LLMProviderConfig] = field(default_factory=dict)
    narrative_allowed_fields: tuple[str, ...] = ()
    min_narrative_context_fields: int = 0

    @property
    def is_production(self) -> bool:
        return self.env == "production"
