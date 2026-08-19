from __future__ import annotations

import json
from typing import Any


class CloudTasksTaskQueue:
    def __init__(
        self,
        *,
        queue_path: str,
        push_endpoint_url: str,
        oidc_service_account_email: str,
        oidc_audience: str | None = None,
        client: Any | None = None,
    ) -> None:
        if not oidc_audience:
            raise ValueError("Cloud Tasks OIDC audience must be configured")
        self._queue_path = queue_path
        self._push_endpoint_url = push_endpoint_url
        self._oidc_service_account_email = oidc_service_account_email
        self._oidc_audience = oidc_audience
        self._client = client or self._build_default_client()

    def enqueue(self, submission_id: str) -> None:
        oidc_token: dict[str, str] = {
            "service_account_email": self._oidc_service_account_email,
            "audience": self._oidc_audience,
        }

        task = {
            "http_request": {
                "http_method": "POST",
                "url": self._push_endpoint_url,
                "headers": {"Content-Type": "application/json"},
                "body": json.dumps({"submission_id": submission_id}).encode("utf-8"),
                "oidc_token": oidc_token,
            }
        }
        self._client.create_task(parent=self._queue_path, task=task)

    @staticmethod
    def _build_default_client() -> Any:
        from google.cloud import tasks_v2

        return tasks_v2.CloudTasksClient()
