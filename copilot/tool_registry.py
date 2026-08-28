"""Central registry the Validation Copilot draws its tools from. Tool
descriptions/schemas are generated here from each tool's Pydantic models -
never hand-copied into prompts (see agents/prompts.py's
build_copilot_tool_specs, which just calls CopilotToolRegistry.anthropic_specs()).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Protocol

from pydantic import BaseModel, ValidationError


class CopilotTool(Protocol):
    name: str
    description: str
    input_model: type[BaseModel]
    output_model: type[BaseModel]

    def execute(self, **kwargs: Any) -> BaseModel: ...


@dataclass
class _RegisteredTool:
    name: str
    description: str
    input_model: type[BaseModel]
    output_model: type[BaseModel]
    fn: Callable[..., BaseModel]


class ToolNotFoundError(Exception):
    pass


class CopilotToolRegistry:
    """Holds tool definitions and validates/executes calls by name. The
    Copilot agent loop never calls a Python function directly - only
    through here, so every tool call is schema-validated and every unknown
    tool name is rejected before anything runs (see agents/validation_copilot.py)."""

    def __init__(self) -> None:
        self._tools: dict[str, _RegisteredTool] = {}

    def register(
        self,
        name: str,
        description: str,
        input_model: type[BaseModel],
        output_model: type[BaseModel],
        fn: Callable[..., BaseModel],
    ) -> None:
        if name in self._tools:
            raise ValueError(f"tool already registered: {name}")
        self._tools[name] = _RegisteredTool(name, description, input_model, output_model, fn)

    def has(self, name: str) -> bool:
        return name in self._tools

    def names(self) -> list[str]:
        return list(self._tools.keys())

    def anthropic_specs(self) -> list[dict]:
        """Tool definitions in the shape the Anthropic Messages API expects
        for the `tools` parameter of a conversational (non-forced) tool-use
        call."""
        return [
            {
                "name": t.name,
                "description": t.description,
                "input_schema": t.input_model.model_json_schema(),
            }
            for t in self._tools.values()
        ]

    def call(self, name: str, arguments: dict) -> BaseModel:
        """Validates `arguments` against the tool's input model, executes
        it, and returns its typed output. Raises ToolNotFoundError for an
        unregistered name (never silently ignored) and lets ValidationError/
        any execution error propagate - the agent loop decides how to
        surface that to the model/user."""
        if name not in self._tools:
            raise ToolNotFoundError(f"unknown tool: {name!r}")
        tool = self._tools[name]
        try:
            validated_input = tool.input_model.model_validate(arguments)
        except ValidationError:
            raise
        result = tool.fn(**validated_input.model_dump())
        if not isinstance(result, tool.output_model):
            raise TypeError(f"tool {name!r} returned {type(result)!r}, expected {tool.output_model!r}")
        return result
