from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from .models import Assessment, NarrativeContext


@dataclass(frozen=True)
class ValidationOutcome:
    ok: bool
    reason_code: str
    message: str


@dataclass(frozen=True)
class SemanticValidationFailure(Exception):
    reason_code: str
    message: str

    def __str__(self) -> str:
        return f"{self.reason_code}: {self.message}"


class NarrativeValidator(Protocol):
    def validate(
        self,
        *,
        text: str,
        context: NarrativeContext,
        assessment: Assessment,
    ) -> ValidationOutcome:
        ...


class GenericNarrativeValidator:
    def __init__(self, deny_list_categories: dict[str, tuple[str, ...]] | None = None) -> None:
        self._deny_list_categories = deny_list_categories or {}

    def validate(
        self,
        *,
        text: str,
        context: NarrativeContext,
        assessment: Assessment,
    ) -> ValidationOutcome:
        lowered_text = text.lower()
        if assessment.qualification.lower() not in lowered_text:
            return ValidationOutcome(
                ok=False,
                reason_code="QUALIFICATION_MISMATCH",
                message="Narrative does not include the deterministic qualification label",
            )

        context_tokens = " ".join(
            str(value).lower() for value in context.applicant_fields.values() if value is not None
        )
        for category, tokens in self._deny_list_categories.items():
            for token in tokens:
                lowered_token = token.lower()
                if lowered_token in lowered_text and lowered_token not in context_tokens:
                    return ValidationOutcome(
                        ok=False,
                        reason_code="DENY_LIST_VIOLATION",
                        message=f"Narrative introduced deny-listed content in category {category}",
                    )

        return ValidationOutcome(ok=True, reason_code="PASSED", message="Narrative is grounded")
