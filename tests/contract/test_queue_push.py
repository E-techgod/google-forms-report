from __future__ import annotations

import json
import logging
from unittest.mock import patch
from typing import Any

from src.adapters.queue import CloudTasksTaskQueue
from src.api import (
    InvalidOIDCTokenError,
    OIDCVerificationError,
    QueuePushHandler,
    QueuePushRequest,
)


class _RecordingWorker:
    def __init__(
        self,
        *,
        failure: Exception | None = None,
        rejected_push_failure: Exception | None = None,
    ) -> None:
        self.calls: list[str] = []
        self.rejected_push_calls: list[dict[str, str]] = []
        self._failure = failure
        self._rejected_push_failure = rejected_push_failure

    def process_submission(self, submission_id: str) -> None:
        self.calls.append(submission_id)
        if self._failure is not None:
            raise self._failure

    def record_rejected_push(self, submission_id: str, *, reason_code: str, message: str) -> None:
        if self._rejected_push_failure is not None:
            raise self._rejected_push_failure
        self.rejected_push_calls.append(
            {
                "submission_id": submission_id,
                "reason_code": reason_code,
                "message": message,
            }
        )


class _Verifier:
    def __init__(
        self,
        *,
        should_fail: bool = False,
        failure: Exception | None = None,
    ) -> None:
        self.tokens: list[str] = []
        self._should_fail = should_fail
        self._failure = failure

    def verify(self, token: str) -> dict[str, Any]:
        self.tokens.append(token)
        if self._failure is not None:
            raise self._failure
        if self._should_fail:
            raise InvalidOIDCTokenError("bad token")
        return {"email": "queue-invoker@example.invalid"}


def _post(endpoint: QueuePushHandler, *, payload: bytes, authorization: str | None = None) -> int:
    headers = {"Content-Type": "application/json"}
    if authorization is not None:
        headers["Authorization"] = authorization
    response = endpoint.handle(QueuePushRequest(method="POST", headers=headers, body=payload))
    return response.status_code


def test_queue_push_rejects_missing_oidc_token_before_worker_call(caplog: Any) -> None:
    worker = _RecordingWorker()
    endpoint = QueuePushHandler(worker=worker, token_verifier=_Verifier())
    caplog.set_level(logging.WARNING)

    status = _post(endpoint, payload=json.dumps({"submission_id": "submission-1"}).encode("utf-8"))

    assert status == 204
    assert worker.calls == []
    assert worker.rejected_push_calls == [
        {
            "submission_id": "submission-1",
            "reason_code": "MISSING_OIDC_TOKEN",
            "message": "Queue push rejected: missing OIDC token",
        }
    ]
    assert "queue_push_rejected_missing_token" in caplog.text


def test_queue_push_rejects_invalid_oidc_token_before_worker_call(caplog: Any) -> None:
    worker = _RecordingWorker()
    verifier = _Verifier(should_fail=True)
    endpoint = QueuePushHandler(worker=worker, token_verifier=verifier)
    caplog.set_level(logging.WARNING)

    status = _post(
        endpoint,
        payload=json.dumps({"submission_id": "submission-1"}).encode("utf-8"),
        authorization="Bearer invalid-token",
    )

    assert status == 204
    assert verifier.tokens == ["invalid-token"]
    assert worker.calls == []
    assert worker.rejected_push_calls == [
        {
            "submission_id": "submission-1",
            "reason_code": "INVALID_OIDC_TOKEN",
            "message": "Queue push rejected: invalid OIDC token",
        }
    ]
    assert "queue_push_rejected_invalid_token" in caplog.text


def test_queue_push_skips_rejected_push_attribution_when_body_is_unparseable(caplog: Any) -> None:
    worker = _RecordingWorker()
    endpoint = QueuePushHandler(worker=worker, token_verifier=_Verifier())
    caplog.set_level(logging.WARNING)

    status = _post(endpoint, payload=b"{not-json")

    assert status == 204
    assert worker.calls == []
    assert worker.rejected_push_calls == []
    assert "queue_push_rejected_missing_token" in caplog.text


def test_queue_push_returns_204_when_rejected_push_attribution_raises(caplog: Any) -> None:
    worker = _RecordingWorker(rejected_push_failure=RuntimeError("alert sink unavailable"))
    invalid_verifier = _Verifier(should_fail=True)
    endpoint = QueuePushHandler(worker=worker, token_verifier=invalid_verifier)
    caplog.set_level(logging.ERROR)

    missing_token_status = _post(
        endpoint,
        payload=json.dumps({"submission_id": "submission-1"}).encode("utf-8"),
    )
    invalid_token_status = _post(
        endpoint,
        payload=json.dumps({"submission_id": "submission-1"}).encode("utf-8"),
        authorization="Bearer invalid-token",
    )

    assert missing_token_status == 204
    assert invalid_token_status == 204
    assert worker.calls == []
    assert worker.rejected_push_calls == []
    assert invalid_verifier.tokens == ["invalid-token"]
    assert "queue_push_rejected_attribution_failed error_type=RuntimeError error=alert sink unavailable" in caplog.text
    assert '"submission_id": "submission-1"' not in caplog.text


def test_queue_push_returns_500_when_token_verification_infrastructure_fails(caplog: Any) -> None:
    worker = _RecordingWorker()
    verifier = _Verifier(failure=OIDCVerificationError("cert fetch failed"))
    endpoint = QueuePushHandler(worker=worker, token_verifier=verifier)
    caplog.set_level(logging.ERROR)

    status = _post(
        endpoint,
        payload=json.dumps({"submission_id": "submission-1"}).encode("utf-8"),
        authorization="Bearer valid-token",
    )

    assert status == 500
    assert verifier.tokens == ["valid-token"]
    assert worker.calls == []
    assert "queue_push_token_verification_failed" in caplog.text


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


def test_cloud_tasks_queue_requires_oidc_audience() -> None:
    client = _RecordingCloudTasksClient()

    try:
        CloudTasksTaskQueue(
            queue_path="projects/test-project/locations/us-central1/queues/submissions",
            push_endpoint_url="https://worker.example.invalid/tasks/push",
            oidc_service_account_email="queue-invoker@test-project.iam.gserviceaccount.com",
            oidc_audience="",
            client=client,
        )
    except ValueError as exc:
        assert str(exc) == "Cloud Tasks OIDC audience must be configured"
    else:
        raise AssertionError("expected ValueError for missing OIDC audience")


def test_cloud_tasks_queue_requires_oidc_audience_when_none() -> None:
    client = _RecordingCloudTasksClient()

    try:
        CloudTasksTaskQueue(
            queue_path="projects/test-project/locations/us-central1/queues/submissions",
            push_endpoint_url="https://worker.example.invalid/tasks/push",
            oidc_service_account_email="queue-invoker@test-project.iam.gserviceaccount.com",
            oidc_audience=None,
            client=client,
        )
    except ValueError as exc:
        assert str(exc) == "Cloud Tasks OIDC audience must be configured"
    else:
        raise AssertionError("expected ValueError for None OIDC audience")


def test_google_oidc_token_verifier_requires_audience() -> None:
    from src.api import GoogleOIDCTokenVerifier

    try:
        GoogleOIDCTokenVerifier(
            audience="",
            service_account_email="queue-invoker@test-project.iam.gserviceaccount.com",
        )
    except ValueError as exc:
        assert str(exc) == "OIDC audience must be configured"
    else:
        raise AssertionError("expected ValueError for missing OIDC audience")


def test_google_oidc_token_verifier_requires_audience_when_none() -> None:
    from src.api import GoogleOIDCTokenVerifier

    try:
        GoogleOIDCTokenVerifier(
            audience=None,
            service_account_email="queue-invoker@test-project.iam.gserviceaccount.com",
        )
    except ValueError as exc:
        assert str(exc) == "OIDC audience must be configured"
    else:
        raise AssertionError("expected ValueError for None OIDC audience")


def test_google_oidc_token_verifier_treats_malformed_cert_response_as_infrastructure_failure() -> None:
    from src.api import GoogleOIDCTokenVerifier

    class _MalformedCertResponse:
        status = 200
        data = b"{not-json"

    class _MalformedCertRequest:
        def __call__(self, url: str, method: str = "GET"):
            return _MalformedCertResponse()

    verifier = GoogleOIDCTokenVerifier(
        audience="https://worker.example.invalid/tasks/push",
        service_account_email="queue-invoker@test-project.iam.gserviceaccount.com",
        request=_MalformedCertRequest(),
    )

    try:
        verifier.verify("token-value")
    except OIDCVerificationError as exc:
        assert str(exc) == "OIDC token verification infrastructure failure"
    else:
        raise AssertionError("expected malformed cert response to be treated as infrastructure failure")


def test_queue_push_returns_500_when_google_auth_import_fails() -> None:
    from src.api import GoogleOIDCTokenVerifier

    def _status_for_import_failure(
        module_name: str,
        *,
        matching_fromlist: tuple[str, ...] | None = None,
        preload_requests_module: bool = False,
    ) -> tuple[int, list[tuple[str, tuple[str, ...]]]]:
        real_import = __import__
        triggered_imports: list[tuple[str, tuple[str, ...]]] = []

        if preload_requests_module:
            from google.auth.transport.requests import Request as _Request  # noqa: F401

        def _raising_import(name, globals=None, locals=None, fromlist=(), level=0):
            normalized_fromlist = tuple(fromlist or ())
            matches_name = name == module_name
            matches_fromlist = matching_fromlist is None or normalized_fromlist == matching_fromlist
            if matches_name and matches_fromlist:
                triggered_imports.append((name, normalized_fromlist))
                raise ImportError(f"{module_name} broken")
            return real_import(name, globals, locals, fromlist, level)

        verifier = GoogleOIDCTokenVerifier(
            audience="https://worker.example.invalid/tasks/push",
            service_account_email="queue-invoker@test-project.iam.gserviceaccount.com",
        )
        endpoint = QueuePushHandler(worker=_RecordingWorker(), token_verifier=verifier)

        with patch("builtins.__import__", side_effect=_raising_import):
            status = _post(
                endpoint,
                payload=json.dumps({"submission_id": "submission-1"}).encode("utf-8"),
                authorization="Bearer valid-token",
            )
        return status, triggered_imports

    google_auth_status, google_auth_imports = _status_for_import_failure("google.auth")
    requests_status, requests_imports = _status_for_import_failure("google.auth.transport.requests")
    oauth2_status, oauth2_imports = _status_for_import_failure(
        "google.oauth2",
        matching_fromlist=("id_token",),
        preload_requests_module=True,
    )

    assert google_auth_status == 500
    assert google_auth_imports == [("google.auth", ("exceptions",))]
    assert requests_status == 500
    assert requests_imports == [("google.auth.transport.requests", ("Request",))]
    assert oauth2_status == 500
    assert oauth2_imports == [("google.oauth2", ("id_token",))]
