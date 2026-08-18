from __future__ import annotations

from typing import Protocol


class SecretProvider(Protocol):
    def get(self, secret_ref: str) -> str:
        ...


class InMemorySecretProvider:
    def __init__(self, values: dict[str, str] | None = None) -> None:
        self._values = values or {}

    def get(self, secret_ref: str) -> str:
        return self._values[secret_ref]
