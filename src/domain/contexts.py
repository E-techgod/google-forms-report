from __future__ import annotations

from datetime import datetime

from .models import (
    Assessment,
    ClientReportContext,
    InternalReportContext,
    Narrative,
    NarrativeContext,
    NormalizedApplication,
)


def build_narrative_context(
    application: NormalizedApplication,
    assessment: Assessment,
    *,
    allowed_application_fields: tuple[str, ...],
) -> NarrativeContext:
    applicant_fields = {
        key: application.fields[key]
        for key in allowed_application_fields
        if key in application.fields and application.fields[key] is not None
    }
    return NarrativeContext(
        submission_id=application.submission_id,
        applicant_fields=applicant_fields,
        reasons=assessment.reasons,
        qualification=assessment.qualification,
        rule_version=assessment.rule_version,
    )


def count_populated_context_fields(context: NarrativeContext) -> int:
    return sum(1 for value in context.applicant_fields.values() if value not in (None, ""))


def should_use_fallback_narrative(context: NarrativeContext, minimum_fields: int) -> bool:
    return count_populated_context_fields(context) < minimum_fields


def build_fallback_narrative(
    context: NarrativeContext,
    *,
    prompt_version: str,
    attempt_number: int,
    now: datetime,
) -> Narrative:
    reasons = ", ".join(context.reasons) if context.reasons else "No triggered reasons recorded."
    text = f"Qualification: {context.qualification}. Reasons: {reasons}"
    return Narrative(
        submission_id=context.submission_id,
        attempt_number=attempt_number,
        provider="deterministic-fallback",
        model="template-only",
        prompt_version=prompt_version,
        raw_output=text,
        validation_result="PASSED",
        text=text,
        generated_at=now,
        used_fallback=True,
    )


def build_internal_report_context(
    application: NormalizedApplication,
    assessment: Assessment,
    narrative: Narrative,
) -> InternalReportContext:
    return InternalReportContext(
        submission_id=application.submission_id,
        normalized_fields=dict(application.fields),
        rules_triggered=assessment.rules_triggered,
        reasons=assessment.reasons,
        qualification=assessment.qualification,
        rule_version=assessment.rule_version,
        narrative_text=narrative.text,
        provider=narrative.provider,
        model=narrative.model,
    )


def build_client_report_context(
    application: NormalizedApplication,
    narrative: Narrative,
    assessment: Assessment,
    *,
    allowed_application_fields: tuple[str, ...],
) -> ClientReportContext:
    allowed_fields = {
        key: application.fields[key]
        for key in allowed_application_fields
        if key in application.fields and application.fields[key] is not None
    }
    return ClientReportContext(
        submission_id=application.submission_id,
        allowed_fields=allowed_fields,
        narrative_text=narrative.text,
        qualification_label=assessment.qualification,
    )
