from __future__ import annotations

from dataclasses import dataclass

from src.domain.models import PipelineStage, ReportType

from .models import AppConfig


@dataclass(frozen=True)
class ReadinessFailure(Exception):
    stage: PipelineStage
    reason_code: str
    message: str
    retryable: bool = False

    def __str__(self) -> str:
        return f"{self.stage}:{self.reason_code}:{self.message}"


@dataclass(frozen=True)
class StartupReadinessError(Exception):
    reason_code: str
    message: str

    def __str__(self) -> str:
        return f"{self.reason_code}: {self.message}"


class ReadinessGate:
    def __init__(self, config: AppConfig) -> None:
        self._config = config

    def validate_startup(self) -> None:
        if not self._config.is_production:
            return
        version = self._config.active_alert_channel_version
        channel = self._config.alert_channels.get(version) if version else None
        if channel is None or not channel.approved_for_production:
            raise StartupReadinessError(
                reason_code="ALERT_CHANNEL_NOT_CONFIGURED",
                message="Production startup requires an approved alert channel",
            )

    def ensure_stage_ready(self, stage: PipelineStage, *, form_id: str | None = None) -> None:
        if not self._config.is_production:
            return
        if stage == PipelineStage.NORMALIZATION:
            version = self._config.active_form_schema_versions.get(form_id or "")
            mapping = self._config.form_schema_mappings.get(version) if version else None
            if mapping is None or not mapping.approved_for_production:
                raise ReadinessFailure(
                    stage=stage,
                    reason_code="SCHEMA_NOT_CONFIGURED",
                    message="No approved schema mapping is configured",
                )
            return
        if stage == PipelineStage.CLASSIFICATION:
            ruleset = self._config.rule_sets.get(self._config.active_rule_set_version or "")
            if ruleset is None or not ruleset.approved_for_production:
                raise ReadinessFailure(
                    stage=stage,
                    reason_code="RULES_NOT_CONFIGURED",
                    message="No approved ruleset is configured",
                )
            return
        if stage == PipelineStage.NARRATIVE:
            provider = self._config.llm_provider_configs.get(
                self._config.active_llm_provider_version or ""
            )
            if provider is None or not provider.approved_for_production:
                raise ReadinessFailure(
                    stage=stage,
                    reason_code="LLM_PROVIDER_NOT_CONFIGURED",
                    message="No approved LLM provider is configured",
                )
            prompt = self._config.prompt_templates.get(provider.prompt_version)
            if prompt is None or not prompt.approved_for_production:
                raise ReadinessFailure(
                    stage=stage,
                    reason_code="DRAFT-UNAPPROVED",
                    message="Prompt template is not approved for production",
                )
            return
        if stage == PipelineStage.REPORT:
            for report_type in (ReportType.INTERNAL, ReportType.CLIENT):
                version = self._config.active_report_template_versions.get(report_type)
                template = self._config.report_templates.get((report_type, version or ""))
                if template is None or not template.approved_for_production:
                    raise ReadinessFailure(
                        stage=stage,
                        reason_code="DRAFT-UNAPPROVED",
                        message=f"{report_type.value} report template is not approved",
                    )
            return
        if stage == PipelineStage.DELIVERY:
            routing = self._config.recipient_routings.get(
                self._config.active_recipient_routing_version or ""
            )
            if routing is None or not routing.approved_for_production:
                raise ReadinessFailure(
                    stage=stage,
                    reason_code="RECIPIENTS_NOT_CONFIGURED",
                    message="Recipient routing is not approved",
                )
            allowlist = self._config.client_report_allowlists.get(
                self._config.active_client_allowlist_version or ""
            )
            if allowlist is None or not allowlist.approved_for_production:
                raise ReadinessFailure(
                    stage=stage,
                    reason_code="DRAFT-UNAPPROVED",
                    message="Client report allowlist is not approved",
                )
