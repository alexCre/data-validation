"""Composition root: assembles every Copilot tool into one registry. This
is the only place that needs to know all the tool modules exist."""

from __future__ import annotations

from copilot.tool_registry import CopilotToolRegistry
from copilot.tools import (
    exports,
    field_validation,
    rule_authoring,
    rules,
    run_history,
    validation_results,
    validation_summary,
)


def build_default_registry() -> CopilotToolRegistry:
    registry = CopilotToolRegistry()
    validation_summary.register(registry)
    validation_results.register(registry)
    field_validation.register(registry)
    rules.register(registry)
    run_history.register(registry)
    exports.register(registry)
    rule_authoring.register(registry)
    return registry
