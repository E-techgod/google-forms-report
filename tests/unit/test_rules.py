from datetime import datetime

import pytest

from src.domain.models import NormalizedApplication
from src.domain.rules import ClassificationFailure, FieldEqualsRule, RuleSet, StaticRuleEngine


def test_rule_engine_fails_closed_when_registry_is_empty() -> None:
    engine = StaticRuleEngine({}, None)
    application = NormalizedApplication(
        submission_id="submission-1",
        form_schema_version="schema-v1",
        fields={"risk_flag": "yes"},
    )

    with pytest.raises(ClassificationFailure) as excinfo:
        engine.classify(application, now=datetime(2026, 8, 18))

    assert excinfo.value.reason_code == "RULES_NOT_CONFIGURED"


def test_rule_engine_classifies_with_synthetic_rule() -> None:
    engine = StaticRuleEngine(
        {
            "rules-v1": RuleSet(
                version="rules-v1",
                approved_for_production=True,
                rules=(
                    FieldEqualsRule(
                        code="FLAG-1",
                        field_name="risk_flag",
                        expected_value="yes",
                        reason="Synthetic test reason",
                    ),
                ),
                qualification_if_any_triggered="REVIEW",
                qualification_if_none_triggered="STANDARD",
            )
        },
        "rules-v1",
    )
    application = NormalizedApplication(
        submission_id="submission-1",
        form_schema_version="schema-v1",
        fields={"risk_flag": "yes"},
    )

    assessment = engine.classify(application, now=datetime(2026, 8, 18))

    assert assessment.rule_version == "rules-v1"
    assert assessment.rules_evaluated == ("FLAG-1",)
    assert assessment.rules_triggered == ("FLAG-1",)
    assert assessment.reasons == ("Synthetic test reason",)
    assert assessment.qualification == "REVIEW"
