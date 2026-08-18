from datetime import datetime

from src.domain.contexts import (
    build_client_report_context,
    build_fallback_narrative,
    build_internal_report_context,
    build_narrative_context,
    count_populated_context_fields,
    should_use_fallback_narrative,
)
from src.domain.models import Assessment, Narrative, NormalizedApplication


def test_narrative_context_enforces_allowlist() -> None:
    application = NormalizedApplication(
        submission_id="submission-1",
        form_schema_version="schema-v1",
        fields={"applicant_name": "test-applicant-001", "secret": "internal-only"},
    )
    assessment = Assessment(
        submission_id="submission-1",
        rule_version="rules-v1",
        rules_evaluated=("FLAG-1",),
        rules_triggered=("FLAG-1",),
        reasons=("Synthetic reason",),
        qualification="REVIEW",
        classified_at=datetime(2026, 8, 18),
    )

    context = build_narrative_context(
        application,
        assessment,
        allowed_application_fields=("applicant_name",),
    )

    assert context.applicant_fields == {"applicant_name": "test-applicant-001"}


def test_client_report_context_default_allowlist_keeps_only_required_fields() -> None:
    application = NormalizedApplication(
        submission_id="submission-1",
        form_schema_version="schema-v1",
        fields={"applicant_name": "test-applicant-001", "internal_only": "do-not-leak"},
    )
    assessment = Assessment(
        submission_id="submission-1",
        rule_version="rules-v1",
        rules_evaluated=("FLAG-1",),
        rules_triggered=("FLAG-1",),
        reasons=("Synthetic reason",),
        qualification="REVIEW",
        classified_at=datetime(2026, 8, 18),
    )
    narrative = Narrative(
        submission_id="submission-1",
        attempt_number=1,
        provider="null-llm",
        model="template-only",
        prompt_version="prompt-v1",
        raw_output="Qualification: REVIEW. Reasons: Synthetic reason",
        validation_result="PASSED",
        text="Qualification: REVIEW. Reasons: Synthetic reason",
        generated_at=datetime(2026, 8, 18),
    )

    context = build_client_report_context(
        application,
        narrative,
        assessment,
        allowed_application_fields=(),
    )

    assert context.allowed_fields == {}
    assert context.narrative_text == narrative.text
    assert context.qualification_label == "REVIEW"


def test_internal_report_context_contains_internal_metadata() -> None:
    application = NormalizedApplication(
        submission_id="submission-1",
        form_schema_version="schema-v1",
        fields={"applicant_name": "test-applicant-001"},
    )
    assessment = Assessment(
        submission_id="submission-1",
        rule_version="rules-v1",
        rules_evaluated=("FLAG-1",),
        rules_triggered=("FLAG-1",),
        reasons=("Synthetic reason",),
        qualification="REVIEW",
        classified_at=datetime(2026, 8, 18),
    )
    narrative = Narrative(
        submission_id="submission-1",
        attempt_number=1,
        provider="null-llm",
        model="template-only",
        prompt_version="prompt-v1",
        raw_output="Qualification: REVIEW. Reasons: Synthetic reason",
        validation_result="PASSED",
        text="Qualification: REVIEW. Reasons: Synthetic reason",
        generated_at=datetime(2026, 8, 18),
    )

    context = build_internal_report_context(application, assessment, narrative)

    assert context.rule_version == "rules-v1"
    assert context.rules_triggered == ("FLAG-1",)
    assert context.provider == "null-llm"


def test_minimum_context_floor_triggers_fallback_narrative() -> None:
    application = NormalizedApplication(
        submission_id="submission-1",
        form_schema_version="schema-v1",
        fields={"applicant_name": "test-applicant-001"},
    )
    assessment = Assessment(
        submission_id="submission-1",
        rule_version="rules-v1",
        rules_evaluated=("FLAG-1",),
        rules_triggered=("FLAG-1",),
        reasons=("Synthetic reason",),
        qualification="REVIEW",
        classified_at=datetime(2026, 8, 18),
    )
    context = build_narrative_context(application, assessment, allowed_application_fields=())

    assert count_populated_context_fields(context) == 0
    assert should_use_fallback_narrative(context, 1)

    narrative = build_fallback_narrative(
        context,
        prompt_version="prompt-v1",
        attempt_number=1,
        now=datetime(2026, 8, 18),
    )
    assert narrative.used_fallback is True
    assert "Qualification: REVIEW" in narrative.text
