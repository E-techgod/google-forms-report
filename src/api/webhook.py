from __future__ import annotations
from datetime import datetime, timezone

import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Callable
from uuid import uuid4

from src.adapters.forms.parser import FormPayloadParser, InvalidPayloadError
from src.domain.models import RawFormSubmission, SubmissionState, SubmissionStatus
from src.persistence.interfaces import RepositoryBundle
from src.workflows.queue import TaskQueue

LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True)
class WebhookResponse:
    status_code: int
    submission_status: SubmissionStatus
    submission_id: str | None = None


class WebhookReceiver:
    def __init__(
        self,
        *,
        parser: FormPayloadParser,
        repositories: RepositoryBundle,
        queue: TaskQueue,
        now_factory: Callable[[], datetime] | None = None,
    ) -> None:
        self._parser = parser
        self._repositories = repositories
        self._queue = queue
        self._now_factory = lambda: datetime.now(timezone.utc)

    def handle(self, payload: dict[str, Any]) -> WebhookResponse:
        try:
            parsed = self._parser.parse(payload)
        except InvalidPayloadError:
            LOGGER.warning("submission_rejected_invalid")
            return WebhookResponse(
                status_code=400,
                submission_status=SubmissionStatus.REJECTED_INVALID,
            )

        existing = self._repositories.raw_submissions.find_by_response(
            parsed.form_id,
            parsed.response_id,
        )
        if existing is not None:
            LOGGER.info(
                "submission_deduplicated form_id=%s response_id=%s",
                parsed.form_id,
                parsed.response_id,
            )
            return WebhookResponse(
                status_code=200,
                submission_status=SubmissionStatus.REJECTED_DUPLICATE,
                submission_id=existing.submission_id,
            )

        submission_id = str(uuid4())
        raw_submission = RawFormSubmission(
            submission_id=submission_id,
            form_id=parsed.form_id,
            response_id=parsed.response_id,
            received_at=self._now_factory(),
            raw_payload=parsed.raw_payload,
            form_schema_version_at_receipt=parsed.form_schema_version,
        )
        inserted = self._repositories.raw_submissions.insert(raw_submission)
        if not inserted:
            return WebhookResponse(
                status_code=200,
                submission_status=SubmissionStatus.REJECTED_DUPLICATE,
                submission_id=submission_id,
            )

        self._repositories.submission_states.create(
            SubmissionState(
                submission_id=submission_id,
                status=SubmissionStatus.RECEIVED,
                updated_at=self._now_factory(),
            )
        )
        self._queue.enqueue(submission_id)
        LOGGER.info(
            "submission_received submission_id=%s form_id=%s response_id=%s",
            submission_id,
            parsed.form_id,
            parsed.response_id,
        )
        return WebhookResponse(
            status_code=202,
            submission_status=SubmissionStatus.RECEIVED,
            submission_id=submission_id,
        )
