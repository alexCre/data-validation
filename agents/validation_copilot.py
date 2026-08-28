"""The Validation Copilot: a bounded conversational tool-use loop over the
Copilot tool registry (copilot/tool_registry.py). Chooses tools, executes
them through the registry (never directly), and returns final text plus a
full trace of what it called - the UI decides what to show a normal user
vs. Developer Mode (see app/pages/copilot.py).

This agent never decides a validation outcome itself - every tool call
reads already-computed, deterministic PASS/FAIL/REVIEW/NOT_APPLICABLE
results (see validation.engine). It also never activates a rule -
request_new_rule only compiles/previews (see copilot/tools/rule_authoring.py).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable

from pydantic import ValidationError

from agents.prompts import build_copilot_system_prompt
from agents.providers.base import LLMProvider
from copilot.tool_registry import CopilotToolRegistry, ToolNotFoundError

MAX_TOOL_STEPS = 5


@dataclass
class ToolCallLogEntry:
    step: int
    tool_name: str
    arguments: dict
    success: bool
    error: str | None = None
    output: dict | None = None


@dataclass
class CopilotTurnResult:
    text: str
    tool_calls: list[ToolCallLogEntry] = field(default_factory=list)
    hit_step_limit: bool = False


class ValidationCopilot:
    def __init__(
        self,
        provider: LLMProvider,
        registry: CopilotToolRegistry,
        system_prompt: str | None = None,
        max_steps: int = MAX_TOOL_STEPS,
    ) -> None:
        self._provider = provider
        self._registry = registry
        self._system_prompt = system_prompt or build_copilot_system_prompt()
        self._max_steps = max_steps

    def run(
        self,
        messages: list[dict],
        on_tool_call: Callable[[ToolCallLogEntry], None] | None = None,
    ) -> CopilotTurnResult:
        """`messages` is the full conversation so far (Anthropic message-
        block format), ending in the newest user message. Returns the final
        assistant text and the tool-call trace for this turn only - the
        caller is responsible for appending the resulting messages (tool_use/
        tool_result/final text) to its own persisted history (see
        copilot/state.py), so a bounded loop here doesn't also have to own
        long-term conversation storage."""
        working_messages = list(messages)
        tool_calls_log: list[ToolCallLogEntry] = []
        tool_specs = self._registry.anthropic_specs()

        for step in range(1, self._max_steps + 1):
            try:
                turn = self._provider.converse(self._system_prompt, working_messages, tool_specs)
            except Exception as e:
                return CopilotTurnResult(
                    text=f"The Copilot couldn't reach the language model: {e}",
                    tool_calls=tool_calls_log,
                )

            if not turn.tool_calls:
                return CopilotTurnResult(text=turn.text or "", tool_calls=tool_calls_log)

            working_messages.append(
                {
                    "role": "assistant",
                    "content": (
                        ([{"type": "text", "text": turn.text}] if turn.text else [])
                        + [
                            {"type": "tool_use", "id": tc.id, "name": tc.name, "input": tc.arguments}
                            for tc in turn.tool_calls
                        ]
                    ),
                }
            )

            tool_result_blocks = []
            for tc in turn.tool_calls:
                entry = ToolCallLogEntry(step=step, tool_name=tc.name, arguments=tc.arguments, success=False)
                is_error = False
                try:
                    output = self._registry.call(tc.name, tc.arguments)
                    content = output.model_dump_json()
                    entry.success = True
                    entry.output = output.model_dump(mode="json")
                except ToolNotFoundError as e:
                    content, is_error = f"Tool error: {e}", True
                    entry.error = str(e)
                except ValidationError as e:
                    content, is_error = f"Invalid arguments for {tc.name}: {e}", True
                    entry.error = str(e)
                except Exception as e:  # a tool executed but failed cleanly (e.g. no validation run yet)
                    content, is_error = f"Tool error: {e}", True
                    entry.error = str(e)

                tool_calls_log.append(entry)
                if on_tool_call:
                    on_tool_call(entry)
                tool_result_blocks.append(
                    {"type": "tool_result", "tool_use_id": tc.id, "content": content, "is_error": is_error}
                )

            working_messages.append({"role": "user", "content": tool_result_blocks})

        return CopilotTurnResult(
            text=(
                "I wasn't able to finish answering that within the allowed number of steps "
                f"({self._max_steps}) - try asking a narrower question."
            ),
            tool_calls=tool_calls_log,
            hit_step_limit=True,
        )
