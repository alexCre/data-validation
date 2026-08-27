"""Builds the LLM prompts for both agentic roles.

Only the natural-language rule text, semantic catalog, and operator catalog
are ever included - never record-level CSV data (see the LLM data boundary
in the master spec, section 2, and tests/test_llm_privacy_boundary.py).
"""

from __future__ import annotations

import json

from catalog.loader import load_schema
from validation.registry import OperatorRegistry

RULE_AUTHORING_SYSTEM_PROMPT = """You are the Rule Authoring Agent for a dMRV data validation system.
You interpret a user's natural-language validation requirement and compile it into a
structured, typed rule expression using ONLY the operators and fields provided to you.

Rules:
- You may only reference fields listed in the semantic catalog below.
- You may only use operators listed in the operator catalog below - never invent one.
- If the requirement needs a capability no listed operator provides, return status
  UNSUPPORTED_CAPABILITY and name the missing capability - do not approximate with an
  unrelated operator.
- If the requirement is ambiguous, return status NEEDS_CLARIFICATION with a specific
  question - do not guess.
- Never compare a field to a null/None literal to test whether it was recorded
  (equals/not_equals/mapped_equals return unknown whenever either side is None, so
  that always evaluates to unknown, never true/false). Use is_present for
  "field X must be present/recorded" requirements instead.
- Otherwise return status COMPILED with a valid expression tree, AND all four of:
  interpretation (one plain-language sentence restating exactly what will be
  checked, for a non-technical user to confirm before it runs), pass_criteria
  (plain language: when this rule PASSes), fail_criteria (plain language: when
  it FAILs), and review_criteria (plain language: when it falls back to
  NEEDS_REVIEW/PASS/FAIL-by-policy due to missing data - state precisely which
  required field(s) being absent trigger this, and if an operator you chose
  (e.g. is_present) never produces an unknown result, say so explicitly rather
  than describing a review case that cannot actually happen). These four
  fields are mandatory whenever status is COMPILED.
"""

CAPABILITY_EXTENSION_SYSTEM_PROMPT = """You are the Capability Extension Agent for a dMRV data
validation system. You are invoked only after the Rule Authoring Agent reported
UNSUPPORTED_CAPABILITY. Specify a reusable, typed operator that would close the gap: purpose,
input/output contract, configuration parameters, edge cases, failure behavior, and suggested
unit tests. When asked to draft an implementation, generate Python code and pytest tests for
review - this code is never executed automatically.
"""


def build_operator_catalog_text(registry: OperatorRegistry) -> str:
    catalog = [
        {
            "name": spec.name,
            "category": spec.category,
            "description": spec.description,
            "input_types": spec.input_types,
            "output_type": spec.output_type,
            "parameters": spec.parameters,
        }
        for spec in registry.catalog()
    ]
    return json.dumps(catalog, indent=2)


def build_semantic_catalog_text() -> str:
    return json.dumps(load_schema(), indent=2)


def build_rule_authoring_user_prompt(user_rule: str, registry: OperatorRegistry) -> str:
    return (
        f"User validation requirement:\n{user_rule}\n\n"
        f"Semantic catalog (canonical tables/fields):\n{build_semantic_catalog_text()}\n\n"
        f"Operator catalog:\n{build_operator_catalog_text(registry)}\n"
    )


def build_capability_gap_user_prompt(rule_text: str, understood_goal: str, missing_capabilities: list[str], registry: OperatorRegistry) -> str:
    return (
        f"Original user requirement:\n{rule_text}\n\n"
        f"Understood goal:\n{understood_goal}\n\n"
        f"Missing capabilities: {', '.join(missing_capabilities)}\n\n"
        f"Existing operator catalog (for context on style/contract conventions):\n"
        f"{build_operator_catalog_text(registry)}\n"
    )


def build_operator_base_interface_text() -> str:
    return (
        "class Operator(Protocol):\n"
        "    def execute(self, *args: Any, **params: Any) -> Any: ...\n\n"
        "Operators are pure, deterministic functions registered via "
        "validation.registry.operator(name, category, description, input_types, "
        "output_type, parameters, examples). They return the typed output value, "
        "or None to signal missing/unknown data (handled by the rule's "
        "missing_data policy)."
    )
