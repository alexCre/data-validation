from __future__ import annotations

from copilot.models import RuleDetailsInput, RuleDetailsOutput
from copilot.tool_registry import CopilotToolRegistry
from copilot.tools._common import rules_lookup


def get_rule_details(rule_id: str) -> RuleDetailsOutput:
    rule = rules_lookup().get(rule_id)
    if rule is None:
        return RuleDetailsOutput(found=False, rule_id=rule_id)
    return RuleDetailsOutput(
        found=True,
        rule_id=rule.rule_id,
        name=rule.name,
        description=rule.description,
        version=rule.version,
        status=rule.status.value,
        missing_data_policy=rule.missing_data.value,
        required_inputs=rule.required_inputs,
    )


def register(registry: CopilotToolRegistry) -> None:
    registry.register(
        "get_rule_details",
        "Plain-language details for one rule id (name, description, version, status, missing-data "
        "policy, required inputs). Does not expose the raw DSL expression tree.",
        RuleDetailsInput,
        RuleDetailsOutput,
        get_rule_details,
    )
