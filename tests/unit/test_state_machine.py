from src.domain.models import SubmissionStatus
from src.domain.state_machine import is_valid_transition


def test_state_machine_allows_stage_retry_success() -> None:
    assert is_valid_transition(SubmissionStatus.NARRATIVE_FAILED, SubmissionStatus.NARRATIVE_READY)


def test_state_machine_rejects_skipped_transition() -> None:
    assert not is_valid_transition(SubmissionStatus.RECEIVED, SubmissionStatus.REPORTS_READY)


def test_state_machine_rejects_terminal_transition() -> None:
    assert not is_valid_transition(SubmissionStatus.COMPLETED, SubmissionStatus.REPORTS_READY)


def test_state_machine_rejects_completed_without_deliveries() -> None:
    assert not is_valid_transition(
        SubmissionStatus.REPORTS_READY,
        SubmissionStatus.COMPLETED,
        deliveries_complete=False,
    )
