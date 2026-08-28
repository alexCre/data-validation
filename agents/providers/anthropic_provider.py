from __future__ import annotations

import os
from typing import TypeVar

from dotenv import load_dotenv
from pydantic import BaseModel

from agents.providers.base import ConversationTurn, ToolCallRequest

# Loaded here (not just documented in README) so ANTHROPIC_API_KEY/DMRV_LLM_MODEL/
# DEVELOPER_MODE from a local .env reach os.environ regardless of entry point
# (Streamlit app, a script, tests) - never overrides a real env var already set.
load_dotenv()

T = TypeVar("T", bound=BaseModel)

DEFAULT_MODEL_ENV_VAR = "DMRV_LLM_MODEL"
DEFAULT_MODEL = "claude-sonnet-5"


class AnthropicProvider:
    """Structured-output provider backed by the Anthropic Messages API,
    using a single forced tool call to get a JSON payload matching
    `response_model`'s schema. Model name is configurable via the
    DMRV_LLM_MODEL env var, never hard-coded deep in the codebase.
    """

    def __init__(self, api_key: str | None = None, model: str | None = None) -> None:
        import anthropic

        self._client = anthropic.Anthropic(api_key=api_key or os.environ["ANTHROPIC_API_KEY"])
        self._model = model or os.environ.get(DEFAULT_MODEL_ENV_VAR, DEFAULT_MODEL)

    def structured_generate(
        self, system_prompt: str, user_prompt: str, response_model: type[T], max_tokens: int = 4096
    ) -> T:
        schema = response_model.model_json_schema()
        tool_name = f"emit_{response_model.__name__.lower()}"
        response = self._client.messages.create(
            model=self._model,
            max_tokens=max_tokens,
            system=system_prompt,
            messages=[{"role": "user", "content": user_prompt}],
            tools=[{"name": tool_name, "description": f"Emit a {response_model.__name__}.", "input_schema": schema}],
            tool_choice={"type": "tool", "name": tool_name},
        )
        for block in response.content:
            if block.type == "tool_use" and block.name == tool_name:
                if response.stop_reason == "max_tokens":
                    # The tool_use JSON was very likely cut off mid-generation
                    # (this bites GeneratedOperatorDraft in particular - full
                    # implementation_code + test_code can be long) - fail
                    # loudly here with a clear cause rather than let a cryptic
                    # pydantic "field required" error surface downstream.
                    raise RuntimeError(
                        f"Anthropic response for {response_model.__name__} was truncated at "
                        f"max_tokens={max_tokens} before completing - raise max_tokens and retry."
                    )
                return response_model.model_validate(block.input)
        raise RuntimeError("Anthropic response did not include the expected tool_use block")

    def converse(self, system_prompt: str, messages: list[dict], tools: list[dict]) -> ConversationTurn:
        response = self._client.messages.create(
            model=self._model,
            max_tokens=2048,
            system=system_prompt,
            messages=messages,
            tools=tools,
            tool_choice={"type": "auto"},
        )
        text_parts: list[str] = []
        tool_calls: list[ToolCallRequest] = []
        for block in response.content:
            if block.type == "text":
                text_parts.append(block.text)
            elif block.type == "tool_use":
                tool_calls.append(ToolCallRequest(id=block.id, name=block.name, arguments=block.input))
        return ConversationTurn(text="\n".join(text_parts) if text_parts else None, tool_calls=tool_calls)


def is_configured() -> bool:
    return bool(os.environ.get("ANTHROPIC_API_KEY"))
