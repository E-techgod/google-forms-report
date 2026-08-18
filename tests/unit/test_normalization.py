from datetime import datetime

import pytest

from src.config.models import FormFieldMapping, FormSchemaMapping
from src.domain.models import RawFormSubmission
from src.domain.normalization import NormalizationError, normalize_submission


def test_normalize_submission_maps_fields_and_warnings() -> None:
    raw_submission = RawFormSubmission(
        submission_id="submission-1",
        form_id="form-1",
        response_id="response-1",
        received_at=datetime(2026, 8, 18),
        raw_payload={"answers": {"name": "test-applicant-001"}},
        form_schema_version_at_receipt="schema-v1",
    )
    mapping = FormSchemaMapping(
        version="schema-v1",
        form_id="form-1",
        approved_for_production=True,
        fields=(
            FormFieldMapping("name", "applicant_name", True),
            FormFieldMapping("age", "age", False, transform="int"),
        ),
    )

    normalized = normalize_submission(raw_submission, mapping)

    assert normalized.fields["applicant_name"] == "test-applicant-001"
    assert normalized.fields["age"] is None
    assert normalized.normalization_warnings == ("Optional field age missing",)


def test_normalize_submission_fails_on_missing_required_field() -> None:
    raw_submission = RawFormSubmission(
        submission_id="submission-1",
        form_id="form-1",
        response_id="response-1",
        received_at=datetime(2026, 8, 18),
        raw_payload={"answers": {}},
        form_schema_version_at_receipt="schema-v1",
    )
    mapping = FormSchemaMapping(
        version="schema-v1",
        form_id="form-1",
        approved_for_production=True,
        fields=(FormFieldMapping("name", "applicant_name", True),),
    )

    with pytest.raises(NormalizationError) as excinfo:
        normalize_submission(raw_submission, mapping)

    assert excinfo.value.reason_code == "REQUIRED_FIELD_MISSING"
