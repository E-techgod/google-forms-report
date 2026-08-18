from __future__ import annotations

from datetime import datetime

from src.domain.models import (
    DeliveryStatus,
    PipelineStage,
    ReportType,
    StageError,
    SubmissionStatus,
)


def serialize_attempt_counts(attempt_counts: dict[PipelineStage, int]) -> dict[str, int]:
    return {stage.value: count for stage, count in attempt_counts.items()}


def deserialize_attempt_counts(payload: dict[str, int] | None) -> dict[PipelineStage, int]:
    if not payload:
        return {}
    return {PipelineStage(stage): count for stage, count in payload.items()}


def serialize_stage_error(error: StageError | None) -> dict[str, object] | None:
    if error is None:
        return None
    return {
        "stage": error.stage.value,
        "reason_code": error.reason_code,
        "retryable": error.retryable,
        "message": error.message,
        "attempt_count": error.attempt_count,
        "occurred_at": error.occurred_at.isoformat(),
    }


def deserialize_stage_error(payload: dict[str, object] | None) -> StageError | None:
    if payload is None:
        return None
    return StageError(
        stage=PipelineStage(str(payload["stage"])),
        reason_code=str(payload["reason_code"]),
        retryable=bool(payload["retryable"]),
        message=str(payload["message"]),
        attempt_count=int(payload["attempt_count"]),
        occurred_at=_coerce_datetime(payload["occurred_at"]),
    )


def serialize_report_type(report_type: ReportType) -> str:
    return report_type.value


def serialize_delivery_status(status: DeliveryStatus) -> str:
    return status.value


def serialize_submission_status(status: SubmissionStatus) -> str:
    return status.value


def _coerce_datetime(value: object) -> datetime:
    if isinstance(value, datetime):
        return value
    if isinstance(value, str):
        return datetime.fromisoformat(value)
    raise TypeError(f"Unsupported datetime payload: {value!r}")
