from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol


@dataclass(frozen=True)
class ParsedFormPayload:
    form_id: str
    response_id: str
    form_schema_version: str
    raw_payload: dict[str, Any]


@dataclass(frozen=True)
class InvalidPayloadError(Exception):
    reason_code: str
    message: str


class FormPayloadParser(Protocol):
    def parse(self, payload: dict[str, Any]) -> ParsedFormPayload:
        ...


class SimpleFormPayloadParser:
    def parse(self, payload: dict[str, Any]) -> ParsedFormPayload:
        if not isinstance(payload, dict):
            raise InvalidPayloadError("PAYLOAD_PARSE_ERROR", "Payload must be a dictionary")
        form_id = payload.get("form_id")
        response_id = payload.get("response_id")
        if not form_id or not response_id:
            raise InvalidPayloadError(
                "PAYLOAD_PARSE_ERROR",
                "Payload must include form_id and response_id",
            )
        schema_version = payload.get("form_schema_version", "unconfigured-dev-only")
        return ParsedFormPayload(
            form_id=str(form_id),
            response_id=str(response_id),
            form_schema_version=str(schema_version),
            raw_payload=payload,
        )
