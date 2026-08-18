from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from .models import Assessment, NormalizedApplication


@dataclass(frozen=True)
class RuleEvaluation:
    code: str
    triggered: bool
    reason: str


class RuleEngine(Protocol):
    def classify(self, application: NormalizedApplication, *, now: datetime) -> Assessment:
        ...


class Rule(Protocol):
    code: str

    def evaluate(self, application: NormalizedApplication) -> RuleEvaluation:
        ...


@dataclass(frozen=True)
class FieldEqualsRule:
    code: str
    field_name: str
    expected_value: object
    reason: str

    def evaluate(self, application: NormalizedApplication) -> RuleEvaluation:
        actual_value = application.fields.get(self.field_name)
        return RuleEvaluation(
            code=self.code,
            triggered=actual_value == self.expected_value,
            reason=self.reason,
        )


@dataclass(frozen=True)
class RuleSet:
    version: str
    approved_for_production: bool
    rules: tuple[Rule, ...]
    qualification_if_any_triggered: str
    qualification_if_none_triggered: str


@dataclass(frozen=True)
class ClassificationFailure(Exception):
    reason_code: str
    message: str

    def __str__(self) -> str:
        return f"{self.reason_code}: {self.message}"


class StaticRuleEngine:
    def __init__(self, registry: dict[str, RuleSet], active_version: str | None) -> None:
        self._registry = registry
        self._active_version = active_version

    def classify(self, application: NormalizedApplication, *, now: datetime) -> Assessment:
        if not self._active_version or self._active_version not in self._registry:
            raise ClassificationFailure(
                "RULES_NOT_CONFIGURED",
                "No active ruleset is registered",
            )

        ruleset = self._registry[self._active_version]
        evaluations = tuple(rule.evaluate(application) for rule in ruleset.rules)
        triggered = tuple(result.code for result in evaluations if result.triggered)
        reasons = tuple(result.reason for result in evaluations if result.triggered)
        qualification = (
            ruleset.qualification_if_any_triggered
            if triggered
            else ruleset.qualification_if_none_triggered
        )
        return Assessment(
            submission_id=application.submission_id,
            rule_version=ruleset.version,
            rules_evaluated=tuple(result.code for result in evaluations),
            rules_triggered=triggered,
            reasons=reasons,
            qualification=qualification,
            classified_at=now,
        )
