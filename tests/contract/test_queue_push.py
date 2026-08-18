from __future__ import annotations

import json
from typing import Any

from src.adapters.queue import CloudTasksTaskQueue
from src.api import QueuePushHandler, QueuePushRequest


class _RecordingWorker:
    def __init__(self, *, failure: Exception | None = None) -> None:
        self.calls: list[str] = []
        self._failure = failure

    def process_submission(self, submission_id: str) -> None:
        self.calls.append(submission_id)
        if self._failure is not None:
            raise self._failure


class _Verifier:
    def __init__(self, *, should_fail: bool = False) -> None:
        self.tokens: list[str] = []
        self._should_fail = should_fail

    def verify(self, token: str) -> dict[str, Any]:
        self.tokens.append(token)
        if self._should_fail:
            raise ValueError("bad token")
        return {"email": "queue-invoker@example.invalid"}


def _post(endpoint: QueuePushHandler, *, payload: bytes, authorization: str | None = None) -> int:
    headers = {"Content-Type": "application/json"}
    if authorization is not None:
        headers["Authorization"] = authorization
    response = endpoint.handle(QueuePushRequest(method="POST", headers=headers, body=payload))
    return response.status_code


def test_queue_push_rejects_missing_oidc_token_before_worker_call() -> None:
    worker = _RecordingWorker()
    endpoint = QueuePushHandler(worker=worker, token_verifier=_Verifier())

    status = _post(endpoint, payload=json.dumps({"submission_id": "submission-1"}).encode("utf-8"))

    assert status == 401
    assert worker.calls == []


def test_queue_push_rejects_invalid_oidc_token_before_worker_call() -> None:
    worker = _RecordingWorker()
    verifier = _Verifier(should_fail=True)
    endpoint = QueuePushHandler(worker=worker, token_verifier=verifier)

    status = _post(
        endpoint,
        payload=json.dumps({"submission_id": "submission-1"}).encode("utf-8"),
        authorization="Bearer invalid-token",
    )

    assert status == 401
    assert verifier.tokens == ["invalid-token"]
    assert worker.calls == []


def test_queue_push_accepts_valid_token_and_invokes_worker() -> None:
    worker = _RecordingWorker()
    verifier = _Verifier()
    endpoint = QueuePushHandler(worker=worker, token_verifier=verifier)

    status = _post(
        endpoint,
        payload=json.dumps({"submission_id": "submission-123"}).encode("utf-8"),
        authorization="Bearer valid-token",
    )

    assert status == 204
    assert verifier.tokens == ["valid-token"]
    assert worker.calls == ["submission-123"]


def test_queue_push_returns_retryable_500_when_worker_fails() -> None:
    worker = _RecordingWorker(failure=RuntimeError("transient failure"))
    endpoint = QueuePushHandler(worker=worker, token_verifier=_Verifier())

    status = _post(
        endpoint,
        payload=json.dumps({"submission_id": "submission-123"}).encode("utf-8"),
        authorization="Bearer valid-token",
    )

    assert status == 500
    assert worker.calls == ["submission-123"]


def test_queue_push_returns_400_for_malformed_payload_without_worker_call() -> None:
    worker = _RecordingWorker()
    endpoint = QueuePushHandler(worker=worker, token_verifier=_Verifier())

    status = _post(endpoint, payload=b"{not-json", authorization="Bearer valid-token")

    assert status == 400
    assert worker.calls == []


class _RecordingCloudTasksClient:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    def create_task(self, *, parent: str, task: dict[str, Any]) -> None:
        self.calls.append({"parent": parent, "task": task})


def test_cloud_tasks_queue_constructs_expected_http_task_request() -> None:
    client = _RecordingCloudTasksClient()
    queue = CloudTasksTaskQueue(
        queue_path="projects/test-project/locations/us-central1/queues/submissions",
        push_endpoint_url="https://worker.example.invalid/tasks/push",
        oidc_service_account_email="queue-invoker@test-project.iam.gserviceaccount.com",
        oidc_audience="https://worker.example.invalid/tasks/push",
        client=client,
    )

    queue.enqueue("submission-123")

    assert len(client.calls) == 1
    call = client.calls[0]
    assert call["parent"] == "projects/test-project/locations/us-central1/queues/submissions"
    http_request = call["task"]["http_request"]
    assert http_request["http_method"] == "POST"
    assert http_request["url"] == "https://worker.example.invalid/tasks/push"
    assert http_request["headers"] == {"Content-Type": "application/json"}
    assert json.loads(http_request["body"].decode("utf-8")) == {"submission_id": "submission-123"}
    assert http_request["oidc_token"] == {
        "service_account_email": "queue-invoker@test-project.iam.gserviceaccount.com",
        "audience": "https://worker.example.invalid/tasks/push",
    }
