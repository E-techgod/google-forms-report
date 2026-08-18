from __future__ import annotations

from dataclasses import dataclass

from src.config.models import FormSchemaMapping

from .models import NormalizedApplication, RawFormSubmission, ScalarValue


@dataclass(frozen=True)
class NormalizationError(Exception):
    reason_code: str
    message: str

    def __str__(self) -> str:
        return f"{self.reason_code}: {self.message}"


def _coerce_value(value: object, transform: str) -> ScalarValue:
    if value is None:
        return None
    if transform == "identity":
        if isinstance(value, (str, int, float, bool)):
            return value
        return str(value)
    if transform == "string":
        return str(value)
    if transform == "int":
        return int(value)
    if transform == "float":
        return float(value)
    if transform == "bool":
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            return value.strip().lower() in {"true", "1", "yes", "si"}
        return bool(value)
    raise NormalizationError("UNSUPPORTED_TRANSFORM", f"Unsupported transform {transform}")


def normalize_submission(
    raw_submission: RawFormSubmission,
    schema_mapping: FormSchemaMapping,
) -> NormalizedApplication:
    answers = raw_submission.raw_payload.get("answers")
    if not isinstance(answers, dict):
        raise NormalizationError("PAYLOAD_PARSE_ERROR", "Payload answers must be a dictionary")

    normalized_fields: dict[str, ScalarValue] = {}
    warnings: list[str] = []
    for field in schema_mapping.fields:
        source_value = answers.get(field.source_key)
        if source_value in (None, ""):
            if field.required:
                raise NormalizationError(
                    "REQUIRED_FIELD_MISSING",
                    f"Required field {field.source_key} is missing",
                )
            warnings.append(f"Optional field {field.source_key} missing")
            normalized_fields[field.target_key] = None
            continue
        normalized_fields[field.target_key] = _coerce_value(source_value, field.transform)

    return NormalizedApplication(
        submission_id=raw_submission.submission_id,
        form_schema_version=schema_mapping.version,
        fields=normalized_fields,
        normalization_warnings=tuple(warnings),
    )
