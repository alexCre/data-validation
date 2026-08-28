"""request_new_rule - hands off to the existing Rule Authoring Agent. The
Copilot never activates a rule: this tool only compiles/previews it. The
full RuleCompilationResult (including the DSL expression tree, which the
LLM doesn't need to see) is cached by request_id so the Copilot page can
hand it to the Rules page's existing Preview/Test/Save/Activate flow -
exactly the same session-state contract app/pages/rules.py already uses.
"""

from __future__ import annotations

import uuid

from agents.models import RuleCompilationResult
from agents.providers.mock_provider import MockProvider
from agents.rule_authoring import RuleAuthoringAgent
from app.components.state import get_rule_authoring_agent
from copilot.models import RequestNewRuleInput, RequestNewRuleOutput
from copilot.tool_registry import CopilotToolRegistry

# request_id -> RuleCompilationResult, for the Rules page hand-off. Session-
# local in practice (single Streamlit process); not meant to survive restarts.
_cache: dict[str, RuleCompilationResult] = {}


def get_cached_compilation_result(request_id: str) -> RuleCompilationResult | None:
    return _cache.get(request_id)


def request_new_rule(rule_text: str) -> RequestNewRuleOutput:
    agent = get_rule_authoring_agent() or RuleAuthoringAgent(MockProvider())
    result = agent.compile_rule(rule_text)

    request_id = uuid.uuid4().hex[:12]
    _cache[request_id] = result

    return RequestNewRuleOutput(
        status=result.status.value,
        request_id=request_id,
        interpretation=result.interpretation,
        required_inputs=result.required_inputs,
        selected_operators=result.selected_operators,
        assumptions=result.assumptions,
        pass_criteria=result.pass_criteria,
        fail_criteria=result.fail_criteria,
        review_criteria=result.review_criteria,
        clarification_questions=result.clarification_questions,
        missing_capabilities=result.missing_capabilities,
        proposed_operator_names=result.proposed_operator_names,
    )


def register(registry: CopilotToolRegistry) -> None:
    registry.register(
        "request_new_rule",
        "Hands a natural-language validation requirement to the Rule Authoring Agent to interpret and "
        "compile. Returns COMPILED (with interpretation/pass-fail-review criteria), NEEDS_CLARIFICATION "
        "(with a specific question), or UNSUPPORTED_CAPABILITY (with the missing capability). Never "
        "activates the rule - the user must still Preview/Test/Approve/Activate it in the Rules page.",
        RequestNewRuleInput,
        RequestNewRuleOutput,
        request_new_rule,
    )
