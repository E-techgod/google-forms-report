from datetime import datetime

from src.domain.models import Assessment, NarrativeContext
from src.domain.validation import GenericNarrativeValidator


def test_validation_fails_when_qualification_is_missing() -> None:
    validator = GenericNarrativeValidator()
    context = NarrativeContext(
        submission_id="submission-1",
        applicant_fields={"applicant_name": "test-applicant-001"},
        reasons=("Synthetic reason",),
        qualification="REVIEW",
        rule_version="rules-v1",
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

    outcome = validator.validate(
        text="This text omits the qualification label entirely.",
        context=context,
        assessment=assessment,
    )

    assert outcome.ok is False
    assert outcome.reason_code == "QUALIFICATION_MISMATCH"


def test_validation_fails_on_deny_list_violation() -> None:
    validator = GenericNarrativeValidator({"medical": ("diagnosis-x",)})
    context = NarrativeContext(
        submission_id="submission-1",
        applicant_fields={"applicant_name": "test-applicant-001"},
        reasons=("Synthetic reason",),
        qualification="REVIEW",
        rule_version="rules-v1",
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

    outcome = validator.validate(
        text="Qualification: REVIEW. The applicant has diagnosis-x.",
        context=context,
        assessment=assessment,
    )

    assert outcome.ok is False
    assert outcome.reason_code == "DENY_LIST_VIOLATION"
