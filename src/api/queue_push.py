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


class InvalidOIDCTokenError(ValueError):
    """Raised when a token is present but fails authentication checks."""


class OIDCVerificationError(RuntimeError):
    """Raised when token verification infrastructure fails."""


class GoogleOIDCTokenVerifier:
    def __init__(
        self,
        *,
        audience: str | None,
        service_account_email: str,
        clock_skew_seconds: int = 0,
        request: Any | None = None,
    ) -> None:
        if not audience:
            raise ValueError("OIDC audience must be configured")
        self._audience = audience
        self._service_account_email = service_account_email
        self._clock_skew_seconds = clock_skew_seconds
        self._request = request

    def verify(self, token: str) -> Mapping[str, Any]:
        try:
            from google.auth import exceptions as google_auth_exceptions
            from google.auth.transport.requests import Request
            from google.oauth2 import id_token
        except ImportError as exc:
            raise OIDCVerificationError("OIDC token verification infrastructure failure") from exc

        request = self._request or Request()
        try:
            claims = id_token.verify_oauth2_token(
                token,
                request,
                audience=self._audience,
                clock_skew_in_seconds=self._clock_skew_seconds,
            )
        except google_auth_exceptions.TransportError as exc:
            raise OIDCVerificationError("OIDC token verification transport failure") from exc
        except (json.JSONDecodeError, UnicodeDecodeError, ImportError) as exc:
            raise OIDCVerificationError("OIDC token verification infrastructure failure") from exc
        except google_auth_exceptions.GoogleAuthError as exc:
            raise InvalidOIDCTokenError("OIDC token verification failed") from exc
        except ValueError as exc:
            raise InvalidOIDCTokenError("OIDC token verification failed") from exc
        if claims.get("email") != self._service_account_email:
            raise InvalidOIDCTokenError("OIDC token service account email mismatch")
        if claims.get("email_verified") is False:
            raise InvalidOIDCTokenError("OIDC token email is not verified")
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
            self._attempt_rejected_push_attribution(
                request.body,
                reason_code="MISSING_OIDC_TOKEN",
                message="Queue push rejected: missing OIDC token",
            )
            return QueuePushResponse(status_code=204)

        try:
            self._token_verifier.verify(token)
        except InvalidOIDCTokenError:
            LOGGER.warning("queue_push_rejected_invalid_token")
            self._attempt_rejected_push_attribution(
                request.body,
                reason_code="INVALID_OIDC_TOKEN",
                message="Queue push rejected: invalid OIDC token",
            )
            return QueuePushResponse(status_code=204)
        except OIDCVerificationError:
            LOGGER.exception("queue_push_token_verification_failed")
            return QueuePushResponse(status_code=500)

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

    def _attempt_rejected_push_attribution(self, body: bytes, *, reason_code: str, message: str) -> None:
        try:
            submission_id = self._extract_submission_id(body)
            if submission_id is None:
                return
            self._worker.record_rejected_push(
                submission_id,
                reason_code=reason_code,
                message=message,
            )
        except Exception as exc:
            LOGGER.exception(
                "queue_push_rejected_attribution_failed error_type=%s error=%s",
                type(exc).__name__,
                exc,
            )

    @staticmethod
    def _extract_submission_id(body: bytes) -> str | None:
        try:
            payload = json.loads(body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            return None
        submission_id = payload.get("submission_id")
        if not isinstance(submission_id, str) or not submission_id:
            return None
        return submission_id
