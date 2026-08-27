from __future__ import annotations

from pydantic import ValidationError

from catalog.loader import known_fields
from agents.models import CompilationStatus, RuleCompilationResult
from agents.prompts import RULE_AUTHORING_SYSTEM_PROMPT, build_rule_authoring_user_prompt
from agents.providers.base import LLMProvider
from validation.dsl.validate import validate_rule
from validation.models import Rule
from validation.registry import OperatorRegistry, registry as default_registry


class RuleAuthoringAgent:
    """Interprets a natural-language validation requirement and compiles it
    into a structured DSL rule. Never validates individual field records -
    that's the deterministic engine's job. Only ever sends the catalog +
    operator metadata + rule text to the LLM, never CSV rows.
    """

    def __init__(self, provider: LLMProvider, operator_registry: OperatorRegistry = default_registry) -> None:
        self._provider = provider
        self._registry = operator_registry

    def compile_rule(self, user_rule: str) -> RuleCompilationResult:
        user_prompt = build_rule_authoring_user_prompt(user_rule, self._registry)
        try:
            result = self._provider.structured_generate(
                RULE_AUTHORING_SYSTEM_PROMPT, user_prompt, RuleCompilationResult
            )
        except ValidationError as e:
            # The provider's structured output didn't match RuleCompilationResult's
            # schema (e.g. a free-text value where an enum was required) - degrade
            # to NEEDS_CLARIFICATION rather than letting this crash the caller.
            return RuleCompilationResult(
                status=CompilationStatus.NEEDS_CLARIFICATION,
                understood_portion=user_rule,
                clarification_questions=[
                    "The agent's response didn't match the expected schema - try rephrasing the requirement."
                ],
                ambiguity_explanation=f"Malformed structured response from the LLM provider: {e}",
            )

        if result.status == CompilationStatus.COMPILED:
            return self._validate_compiled_result(result)
        return result

    def _validate_compiled_result(self, result: RuleCompilationResult) -> RuleCompilationResult:
        """Never accept hallucinated operators/fields as executable - if the
        LLM's COMPILED expression fails DSL validation, downgrade to
        NEEDS_CLARIFICATION rather than letting it through."""
        if result.expression is None:
            return RuleCompilationResult(
                status=CompilationStatus.NEEDS_CLARIFICATION,
                understood_portion=result.interpretation,
                clarification_questions=["The agent reported COMPILED without an expression."],
                ambiguity_explanation="Malformed agent response.",
            )

        probe_rule = Rule(
            rule_id="_PROBE",
            name="probe",
            description="probe",
            required_inputs=result.required_inputs,
            expression=result.expression,
        )
        errors = validate_rule(probe_rule, known_fields())
        for operator_name in result.selected_operators:
            if not self._registry.has(operator_name):
                errors.append(f"selected_operators references unregistered operator: {operator_name!r}")

        if errors:
            return RuleCompilationResult(
                status=CompilationStatus.NEEDS_CLARIFICATION,
                understood_portion=result.interpretation,
                clarification_questions=[
                    "The compiled expression referenced operators/fields outside the "
                    "registry and was rejected: " + "; ".join(errors)
                ],
                ambiguity_explanation="Compiled rule failed DSL validation (possible hallucination).",
            )
        return result
