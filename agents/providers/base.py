from __future__ import annotations

from typing import Protocol, TypeVar

from pydantic import BaseModel

T = TypeVar("T", bound=BaseModel)


class LLMProvider(Protocol):
    """Structured-output LLM abstraction. Implementations must never receive
    record-level CSV data - callers only pass the natural-language rule text
    plus catalog/schema/operator metadata (see agents.rule_authoring)."""

    def structured_generate(
        self, system_prompt: str, user_prompt: str, response_model: type[T], max_tokens: int = 4096
    ) -> T:
        ...
