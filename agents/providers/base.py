from __future__ import annotations

from typing import Any, Protocol, TypeVar

from pydantic import BaseModel, Field

T = TypeVar("T", bound=BaseModel)


class ToolCallRequest(BaseModel):
    id: str
    name: str
    arguments: dict[str, Any] = Field(default_factory=dict)


class ConversationTurn(BaseModel):
    """One assistant turn in a conversational tool-use loop: either final
    text (tool_calls empty) or one or more tool calls to execute before
    continuing (see agents.validation_copilot)."""

    text: str | None = None
    tool_calls: list[ToolCallRequest] = Field(default_factory=list)


class LLMProvider(Protocol):
    """Structured-output LLM abstraction. Implementations must never receive
    record-level CSV data - callers only pass the natural-language rule text
    plus catalog/schema/operator metadata (see agents.rule_authoring)."""

    def structured_generate(
        self, system_prompt: str, user_prompt: str, response_model: type[T], max_tokens: int = 4096
    ) -> T:
        ...

    def converse(self, system_prompt: str, messages: list[dict], tools: list[dict]) -> ConversationTurn:
        """A conversational (non-forced) tool-use turn: given the running
        message history in Anthropic message-block format and a list of
        tool specs (name/description/input_schema), the model may return
        final text, one or more tool calls, or both. Used by the Validation
        Copilot's bounded tool loop (see agents.validation_copilot); the
        Rule Authoring / Capability Extension agents don't use this."""
        ...
