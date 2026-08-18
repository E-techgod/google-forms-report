from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Any, Mapping, Protocol

from src.workflows.worker import Worker

LOGGER = logging.getLogger(__name__)


class OIDCTokenVerifier(Protocol):
    def verify(self, token: str) -> Mapping[str, Any]:
        ...


class GoogleOIDCTokenVerifier:
    def __init__(
        self,
        *,
        audience: str | None,
        service_account_email: str,
        clock_skew_seconds: int = 0,
        request: Any | None = None,
    ) -> None:
        self._audience = audience
        self._service_account_email = service_account_email
        self._clock_skew_seconds = clock_skew_seconds
        self._request = request

    def verify(self, token: str) -> Mapping[str, Any]:
        from google.auth.transport.requests import Request
        from google.oauth2 import id_token

        request = self._request or Request()
        claims = id_token.verify_oauth2_token(
            token,
            request,
            audience=self._audience,
            clock_skew_in_seconds=self._clock_skew_seconds,
        )
        if claims.get("email") != self._service_account_email:
            raise ValueError("OIDC token service account email mismatch")
        if claims.get("email_verified") is False:
            raise ValueError("OIDC token email is not verified")
        return claims


@dataclass(frozen=True)
class QueuePushRequest:
    method: str
    headers: Mapping[str, str]
    body: bytes


@dataclass(frozen=True)
class QueuePushResponse:
    status_code: int
    body: bytes = b""


class QueuePushHandler:
    def __init__(
        self,
        *,
        worker: Worker,
        token_verifier: OIDCTokenVerifier,
    ) -> None:
        self._worker = worker
        self._token_verifier = token_verifier

    def handle(self, request: QueuePushRequest) -> QueuePushResponse:
        if request.method != "POST":
            return QueuePushResponse(status_code=405)

        token = self._extract_bearer_token(request.headers)
        if token is None:
            LOGGER.warning("queue_push_rejected_missing_token")
            return QueuePushResponse(status_code=401)

        try:
            self._token_verifier.verify(token)
        except Exception:
            LOGGER.warning("queue_push_rejected_invalid_token")
            return QueuePushResponse(status_code=401)

        try:
            payload = json.loads(request.body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            return QueuePushResponse(status_code=400)

        submission_id = payload.get("submission_id")
        if not isinstance(submission_id, str) or not submission_id:
            return QueuePushResponse(status_code=400)

        try:
            self._worker.process_submission(submission_id)
        except Exception:
            LOGGER.exception("queue_push_processing_failed submission_id=%s", submission_id)
            return QueuePushResponse(status_code=500)
        return QueuePushResponse(status_code=204)

    @staticmethod
    def _extract_bearer_token(headers: Mapping[str, str]) -> str | None:
        authorization = headers.get("Authorization")
        if authorization is None:
            return None
        scheme, _, token = authorization.partition(" ")
        if scheme != "Bearer" or not token:
            return None
        return token
