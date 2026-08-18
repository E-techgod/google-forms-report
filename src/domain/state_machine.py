from __future__ import annotations

from .models import PipelineStage, SubmissionStatus

SUCCESS_TRANSITIONS: dict[SubmissionStatus, SubmissionStatus] = {
    SubmissionStatus.RECEIVED: SubmissionStatus.NORMALIZED,
    SubmissionStatus.NORMALIZED: SubmissionStatus.CLASSIFIED,
    SubmissionStatus.CLASSIFIED: SubmissionStatus.NARRATIVE_READY,
    SubmissionStatus.NARRATIVE_READY: SubmissionStatus.REPORTS_READY,
    SubmissionStatus.REPORTS_READY: SubmissionStatus.COMPLETED,
}

FAILURE_TRANSITIONS: dict[PipelineStage, SubmissionStatus] = {
    PipelineStage.NORMALIZATION: SubmissionStatus.NORMALIZATION_FAILED,
    PipelineStage.CLASSIFICATION: SubmissionStatus.CLASSIFICATION_FAILED,
    PipelineStage.NARRATIVE: SubmissionStatus.NARRATIVE_FAILED,
    PipelineStage.REPORT: SubmissionStatus.REPORT_FAILED,
    PipelineStage.DELIVERY: SubmissionStatus.DELIVERY_FAILED,
}

STATUS_TO_STAGE: dict[SubmissionStatus, PipelineStage] = {
    SubmissionStatus.RECEIVED: PipelineStage.NORMALIZATION,
    SubmissionStatus.NORMALIZED: PipelineStage.CLASSIFICATION,
    SubmissionStatus.CLASSIFIED: PipelineStage.NARRATIVE,
    SubmissionStatus.NARRATIVE_READY: PipelineStage.REPORT,
    SubmissionStatus.REPORTS_READY: PipelineStage.DELIVERY,
    SubmissionStatus.NORMALIZATION_FAILED: PipelineStage.NORMALIZATION,
    SubmissionStatus.CLASSIFICATION_FAILED: PipelineStage.CLASSIFICATION,
    SubmissionStatus.NARRATIVE_FAILED: PipelineStage.NARRATIVE,
    SubmissionStatus.REPORT_FAILED: PipelineStage.REPORT,
    SubmissionStatus.DELIVERY_FAILED: PipelineStage.DELIVERY,
}

TERMINAL_STATUSES = {
    SubmissionStatus.COMPLETED,
    SubmissionStatus.REJECTED_DUPLICATE,
    SubmissionStatus.REJECTED_INVALID,
    SubmissionStatus.FAILED_PERMANENT,
}

FAILED_TO_SUCCESS: dict[SubmissionStatus, SubmissionStatus] = {
    SubmissionStatus.NORMALIZATION_FAILED: SubmissionStatus.NORMALIZED,
    SubmissionStatus.CLASSIFICATION_FAILED: SubmissionStatus.CLASSIFIED,
    SubmissionStatus.NARRATIVE_FAILED: SubmissionStatus.NARRATIVE_READY,
    SubmissionStatus.REPORT_FAILED: SubmissionStatus.REPORTS_READY,
    SubmissionStatus.DELIVERY_FAILED: SubmissionStatus.COMPLETED,
}


def failure_status_for_stage(stage: PipelineStage) -> SubmissionStatus:
    return FAILURE_TRANSITIONS[stage]


def stage_for_status(status: SubmissionStatus) -> PipelineStage:
    return STATUS_TO_STAGE[status]


def next_stage_for_status(status: SubmissionStatus) -> PipelineStage | None:
    if status in TERMINAL_STATUSES:
        return None
    return STATUS_TO_STAGE.get(status)


def is_terminal_status(status: SubmissionStatus) -> bool:
    return status in TERMINAL_STATUSES


def is_failure_status(status: SubmissionStatus) -> bool:
    return status in FAILURE_TRANSITIONS.values()


def is_valid_transition(
    current: SubmissionStatus,
    new: SubmissionStatus,
    *,
    deliveries_complete: bool = False,
) -> bool:
    if current in TERMINAL_STATUSES:
        return False

    expected_success = SUCCESS_TRANSITIONS.get(current)
    if new == expected_success:
        if new == SubmissionStatus.COMPLETED:
            return deliveries_complete
        return True

    retry_success = FAILED_TO_SUCCESS.get(current)
    if new == retry_success:
        if new == SubmissionStatus.COMPLETED:
            return deliveries_complete
        return True

    current_stage = STATUS_TO_STAGE.get(current)
    if current_stage and new == FAILURE_TRANSITIONS[current_stage]:
        return True

    if is_failure_status(current) and new == SubmissionStatus.FAILED_PERMANENT:
        return True

    return False
