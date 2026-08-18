from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from typing import Any

ScalarValue = str | int | float | bool | None


class PipelineStage(StrEnum):
    NORMALIZATION = "NORMALIZATION"
    CLASSIFICATION = "CLASSIFICATION"
    NARRATIVE = "NARRATIVE"
    REPORT = "REPORT"
    DELIVERY = "DELIVERY"


class SubmissionStatus(StrEnum):
    RECEIVED = "RECEIVED"
    NORMALIZED = "NORMALIZED"
    CLASSIFIED = "CLASSIFIED"
    NARRATIVE_READY = "NARRATIVE_READY"
    REPORTS_READY = "REPORTS_READY"
    COMPLETED = "COMPLETED"
    NORMALIZATION_FAILED = "NORMALIZATION_FAILED"
    CLASSIFICATION_FAILED = "CLASSIFICATION_FAILED"
    NARRATIVE_FAILED = "NARRATIVE_FAILED"
    REPORT_FAILED = "REPORT_FAILED"
    DELIVERY_FAILED = "DELIVERY_FAILED"
    REJECTED_DUPLICATE = "REJECTED_DUPLICATE"
    REJECTED_INVALID = "REJECTED_INVALID"
    FAILED_PERMANENT = "FAILED_PERMANENT"


class ReportType(StrEnum):
    INTERNAL = "INTERNAL"
    CLIENT = "CLIENT"


class DeliveryStatus(StrEnum):
    PENDING = "PENDING"
    SENT = "SENT"
    FAILED = "FAILED"


@dataclass(frozen=True)
class RawFormSubmission:
    submission_id: str
    form_id: str
    response_id: str
    received_at: datetime
    raw_payload: dict[str, Any]
    form_schema_version_at_receipt: str


@dataclass(frozen=True)
class NormalizedApplication:
    submission_id: str
    form_schema_version: str
    fields: dict[str, ScalarValue]
    normalization_warnings: tuple[str, ...] = ()


@dataclass(frozen=True)
class Assessment:
    submission_id: str
    rule_version: str
    rules_evaluated: tuple[str, ...]
    rules_triggered: tuple[str, ...]
    reasons: tuple[str, ...]
    qualification: str
    classified_at: datetime


@dataclass(frozen=True)
class NarrativeContext:
    submission_id: str
    applicant_fields: dict[str, ScalarValue]
    reasons: tuple[str, ...]
    qualification: str
    rule_version: str


@dataclass(frozen=True)
class Narrative:
    submission_id: str
    attempt_number: int
    provider: str
    model: str
    prompt_version: str
    raw_output: str
    validation_result: str
    text: str
    generated_at: datetime
    used_fallback: bool = False


@dataclass(frozen=True)
class InternalReportContext:
    submission_id: str
    normalized_fields: dict[str, ScalarValue]
    rules_triggered: tuple[str, ...]
    reasons: tuple[str, ...]
    qualification: str
    rule_version: str
    narrative_text: str
    provider: str
    model: str


@dataclass(frozen=True)
class ClientReportContext:
    submission_id: str
    allowed_fields: dict[str, ScalarValue]
    narrative_text: str
    qualification_label: str


@dataclass(frozen=True)
class Report:
    submission_id: str
    report_type: ReportType
    template_version: str
    artifact_ref: str
    content: bytes
    generated_at: datetime


@dataclass(frozen=True)
class Delivery:
    submission_id: str
    report_type: ReportType
    recipient: str
    delivery_key: str
    attempt_number: int
    status: DeliveryStatus
    message_id: str | None
    attempted_at: datetime
    sent_at: datetime | None = None
    error_code: str | None = None


@dataclass(frozen=True)
class StageError:
    stage: PipelineStage
    reason_code: str
    retryable: bool
    message: str
    attempt_count: int
    occurred_at: datetime


@dataclass
class SubmissionState:
    submission_id: str
    status: SubmissionStatus
    attempt_counts: dict[PipelineStage, int] = field(default_factory=dict)
    last_error: StageError | None = None
    updated_at: datetime = field(default_factory=datetime.utcnow)
