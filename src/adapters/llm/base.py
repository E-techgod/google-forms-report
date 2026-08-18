from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from typing import Protocol

from src.config.models import LLMProviderConfig, PromptTemplate
from src.domain.models import NarrativeContext


@dataclass(frozen=True)
class LLMGeneration:
    text: str
    raw_output: str
    provider: str
    model: str


class LLMProviderError(Exception):
    pass


class LLMProvider(Protocol):
    def generate_narrative(
        self,
        *,
        context: NarrativeContext,
        prompt_template: PromptTemplate,
        provider_config: LLMProviderConfig,
    ) -> LLMGeneration:
        ...


class NullLLMProvider:
    def __init__(self) -> None:
        self._failures: deque[Exception] = deque()
        self.calls = 0

    def fail_next_call(self, error: Exception) -> None:
        self._failures.append(error)

    def generate_narrative(
        self,
        *,
        context: NarrativeContext,
        prompt_template: PromptTemplate,
        provider_config: LLMProviderConfig,
    ) -> LLMGeneration:
        self.calls += 1
        if self._failures:
            raise self._failures.popleft()
        reasons = ", ".join(context.reasons) if context.reasons else "No triggered reasons recorded."
        text = (
            f"{prompt_template.template_text} "
            f"Qualification: {context.qualification}. Reasons: {reasons}"
        )
        return LLMGeneration(
            text=text,
            raw_output=text,
            provider=provider_config.provider_name,
            model=provider_config.model_name,
        )
