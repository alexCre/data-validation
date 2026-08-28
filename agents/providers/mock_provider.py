"""Deterministic, offline provider for tests and demos without an API key.

Not a real NLU engine - a small set of keyword/pattern heuristics sufficient
to demonstrate the three RuleCompilationResult outcomes and to produce a
plausible CapabilityGapSpec/GeneratedOperatorDraft. A real deployment swaps
this for agents.providers.anthropic_provider.AnthropicProvider without
touching agents.rule_authoring or agents.capability_extension.
"""

from __future__ import annotations

import json
import re
import uuid
from typing import TypeVar

from pydantic import BaseModel

from agents.models import CapabilityGapSpec, CompilationStatus, GeneratedOperatorDraft, RuleCompilationResult
from agents.providers.base import ConversationTurn, ToolCallRequest
from validation.models import ExpressionNode, FieldRef

T = TypeVar("T", bound=BaseModel)

# Keyword -> (missing_capability, proposed operator name). Order matters -
# checked in sequence against the lower-cased rule text.
_CAPABILITY_GAP_TRIGGERS = [
    (("visually show", "visual", "photo should show", "image content"), "photo image-content interpretation", "classify_field_stage"),
    (("boundary", "representative", "too close to the field"), "distance-to-boundary geometry measurement", "distance_to_boundary"),
    (("progression", "backwards", "stage sequence", "must not move backwards"), "semantic crop-stage sequence validation", "validate_stage_progression"),
]

_AFTER_PATTERN = re.compile(r"(\w[\w\s]*?)\s+(?:must be|should be)?\s*after\s+(\w[\w\s]*)", re.IGNORECASE)
# Strips a leading "create/add a (new) rule/validation (that/requiring/saying)"
# request wrapper (e.g. from the Copilot's request_new_rule tool) so the
# X-after-Y match below isn't thrown off by it - e.g. "Create a rule that
# planting must be after straw management" -> "planting must be after straw
# management".
_RULE_REQUEST_PREFIX = re.compile(
    r"^\s*(?:please\s+)?(?:create|add|make)\s+a\s+(?:new\s+)?(?:rule|validation)\b"
    r"(?:\s+(?:that|requiring|saying|stating))?\s*:?\s*",
    re.IGNORECASE,
)


def _extract_user_rule(user_prompt: str) -> str:
    match = re.search(r"User (?:validation requirement|requirement):\n(.*?)\n\n", user_prompt, re.DOTALL)
    return match.group(1).strip() if match else user_prompt


class MockProvider:
    def structured_generate(
        self, system_prompt: str, user_prompt: str, response_model: type[T], max_tokens: int = 4096
    ) -> T:
        if response_model is RuleCompilationResult:
            return self._compile_rule(user_prompt)  # type: ignore[return-value]
        if response_model is CapabilityGapSpec:
            return self._capability_gap_spec(user_prompt)  # type: ignore[return-value]
        if response_model is GeneratedOperatorDraft:
            return self._generated_draft(user_prompt)  # type: ignore[return-value]
        raise NotImplementedError(f"MockProvider has no heuristic for {response_model!r}")

    def converse(self, system_prompt: str, messages: list[dict], tools: list[dict]) -> ConversationTurn:
        """Deterministic keyword routing over the latest message, enough to
        demonstrate/test the Copilot's tool-selection behavior offline: if
        the last message is a tool_result, summarize it and stop (one tool
        call per user turn, never chaining further in the mock); otherwise
        route the newest user text to the one tool it most plausibly needs."""
        last = messages[-1] if messages else None
        if last is not None and _is_tool_result_message(last):
            return ConversationTurn(text=_summarize_tool_result(last), tool_calls=[])

        text = _latest_user_text(messages)
        lowered = text.lower()
        tool_names = {t["name"] for t in tools}

        def _call(name: str, arguments: dict) -> ConversationTurn:
            if name not in tool_names:
                return ConversationTurn(text=f"(mock) no tool named {name!r} is available.")
            return ConversationTurn(tool_calls=[ToolCallRequest(id=f"mock_{uuid.uuid4().hex[:8]}", name=name, arguments=arguments)])

        rule_keywords = ("create a rule", "add a rule", "new rule", "add a validation", "create a validation")
        if any(kw in lowered for kw in rule_keywords):
            return _call("request_new_rule", {"rule_text": text})

        if "download" in lowered or "export" in lowered:
            rule_match = re.search(r"\bC\d+\b", text)
            args = {"mode": "FIELD_SUMMARY"}
            if rule_match:
                args["rule_id"] = rule_match.group(0)
            if "fail" in lowered:
                args["result"] = "FAIL"
            elif "review" in lowered:
                args["result"] = "REVIEW"
            return _call("export_validation_csv", args)

        lot_match = re.search(r"\bLOT-(\S+)\b", text, re.IGNORECASE) or re.search(r"\b(\d{5,})\b", text)
        if lot_match and ("why" in lowered or "fail" in lowered or "issue" in lowered):
            # This dataset's lot_id is a bare numeric string (see catalog/schema.yaml) -
            # a "LOT-<id>" reference (as used in this product's examples) normalizes to
            # just <id>.
            return _call("get_field_findings", {"lot_id": lot_match.group(1), "season_id": "3"})

        rule_match = re.search(r"\bC\d+\b", text)
        if rule_match and ("show" in lowered or "fail" in lowered):
            return _call("get_validation_results", {"rule_id": rule_match.group(0), "result": "FAIL", "limit": 20})

        if "top" in lowered and ("issue" in lowered or "problem" in lowered):
            return _call("get_top_validation_issues", {"limit": 5})

        if "why" in lowered and "fail" in lowered:
            return _call("get_validation_summary", {})

        if "compare" in lowered:
            return _call("get_validation_run_history", {"limit": 5})

        return ConversationTurn(
            text="(offline mock Copilot) I couldn't map that to a supported action - try asking about "
            "validation results, a specific field, or say 'create a rule that ...'."
        )

    def _compile_rule(self, user_prompt: str) -> RuleCompilationResult:
        rule_text = _extract_user_rule(user_prompt)
        rule_text = _RULE_REQUEST_PREFIX.sub("", rule_text).strip() or rule_text
        lowered = rule_text.lower()

        for keywords, capability, operator_name in _CAPABILITY_GAP_TRIGGERS:
            if any(kw in lowered for kw in keywords):
                return RuleCompilationResult(
                    status=CompilationStatus.UNSUPPORTED_CAPABILITY,
                    understood_goal=rule_text,
                    supported_parts=["photo metadata/category validation"],
                    missing_capabilities=[capability],
                    proposed_operator_names=[operator_name],
                    insufficiency_reason=(
                        f"The current operator registry has no {capability} "
                        "capability; this requires a new reusable operator."
                    ),
                )

        # A tiny "X after Y" pattern, enough to demo COMPILED without a real LLM.
        match = _AFTER_PATTERN.search(rule_text)
        if match:
            left, right = match.group(1).strip(), match.group(2).strip()
            left_field = _guess_field(left)
            right_field = _guess_field(right)
            if left_field and right_field:
                expression = ExpressionNode(
                    operator="date_after",
                    args=[FieldRef(field=left_field), FieldRef(field=right_field)],
                )
                return RuleCompilationResult(
                    status=CompilationStatus.COMPILED,
                    expression=expression,
                    interpretation=f"{left_field} must be after {right_field}.",
                    required_inputs=[left_field, right_field],
                    selected_operators=["date_after"],
                    assumptions=[f"Interpreted '{left}' as {left_field} and '{right}' as {right_field}."],
                    pass_criteria=f"PASSes when {left_field} occurs after {right_field}.",
                    fail_criteria=f"FAILs when {left_field} occurs on or before {right_field}.",
                    review_criteria=(
                        f"Falls back to NEEDS_REVIEW when {left_field} or {right_field} "
                        "is missing for that lot/season - there isn't enough data to say pass or fail."
                    ),
                    suggested_missing_data_policy="REVIEW",
                )

        return RuleCompilationResult(
            status=CompilationStatus.NEEDS_CLARIFICATION,
            understood_portion=rule_text,
            clarification_questions=[
                "Which two fields should be compared, and which canonical table are they in?"
            ],
            ambiguity_explanation="The mock provider couldn't map this requirement to a known pattern.",
        )

    def _capability_gap_spec(self, user_prompt: str) -> CapabilityGapSpec:
        capability_match = re.search(r"Missing capabilities: (.+)", user_prompt)
        capability = capability_match.group(1).strip() if capability_match else "unspecified capability"
        goal_match = re.search(r"Understood goal:\n(.*?)\n\n", user_prompt, re.DOTALL)
        goal = goal_match.group(1).strip() if goal_match else "unspecified goal"
        operator_name = re.sub(r"[^a-z0-9]+", "_", capability.lower()).strip("_")

        return CapabilityGapSpec(
            missing_capability=capability,
            proposed_operator_name=operator_name,
            purpose=goal,
            reusable_semantics=f"Deterministically evaluates: {goal}",
            input_contract={"input": "typed input inferred from the requirement"},
            output_contract="bool | None",
            configuration_parameters={},
            edge_cases=["missing input data", "malformed input"],
            failure_behavior="Return None (unknown) on missing/malformed input; let the rule's missing_data policy decide.",
            suggested_unit_tests=["positive case", "negative case", "missing-data case"],
            example_rules=[goal],
        )

    def _generated_draft(self, user_prompt: str) -> GeneratedOperatorDraft:
        name_match = re.search(r"proposed_operator_name['\"]?:\s*['\"]?([a-zA-Z0-9_]+)", user_prompt)
        operator_name = name_match.group(1) if name_match else "new_operator"
        code = (
            f"from validation.registry import operator\n\n\n"
            f"@operator(\n"
            f'    "{operator_name}",\n'
            f'    category="draft",\n'
            f'    description="DRAFT - generated by the Capability Extension Agent; review before use.",\n'
            f"    input_types=[\"any\"],\n"
            f"    output_type=\"bool\",\n"
            f")\n"
            f"def {operator_name}(value) -> bool | None:\n"
            f"    if value is None:\n"
            f"        return None\n"
            f"    raise NotImplementedError(\"draft stub - implement before promotion\")\n"
        )
        tests = (
            f"def test_{operator_name}_missing_data_returns_none():\n"
            f"    from generated_drafts.{operator_name}.operator import {operator_name}\n"
            f"    assert {operator_name}(None) is None\n"
        )
        return GeneratedOperatorDraft(
            operator_name=operator_name,
            implementation_code=code,
            test_code=tests,
            metadata={"category": "draft", "generated_by": "MockProvider"},
            notes="Draft stub only - developer must implement the real logic before promotion.",
        )


def _is_tool_result_message(message: dict) -> bool:
    content = message.get("content")
    if not isinstance(content, list):
        return False
    return any(isinstance(b, dict) and b.get("type") == "tool_result" for b in content)


def _summarize_tool_result(message: dict) -> str:
    for block in message["content"]:
        if isinstance(block, dict) and block.get("type") == "tool_result":
            try:
                data = json.loads(block["content"])
            except (TypeError, ValueError, KeyError):
                return "(mock) Got a tool result I couldn't parse."
            if isinstance(data, dict):
                if "total_field_seasons" in data:
                    return (
                        f"{data.get('total_field_seasons', 0)} field-seasons: "
                        f"{data.get('ready_count', 0)} READY, {data.get('review_required_count', 0)} "
                        f"REVIEW_REQUIRED, {data.get('validation_failed_count', 0)} VALIDATION_FAILED."
                    )
                if "total_matching" in data:
                    return f"{data.get('total_matching', 0)} matching records ({data.get('returned', 0)} shown)."
                if "row_count" in data and "file_path" in data:
                    return f"{data.get('row_count', 0)} records exported."
                if data.get("found") is False:
                    return "I couldn't find that field-season."
                if "findings" in data:
                    return f"Found {len(data.get('findings', []))} rule result(s) for that field-season."
                if "status" in data and data.get("status") in {"COMPILED", "NEEDS_CLARIFICATION", "UNSUPPORTED_CAPABILITY"}:
                    return f"Rule request status: {data['status']}."
            return "(mock) Here's what I found."
    return "(mock) Got a tool result."


def _latest_user_text(messages: list[dict]) -> str:
    for message in reversed(messages):
        if message.get("role") != "user":
            continue
        content = message.get("content")
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            texts = [b.get("text", "") for b in content if isinstance(b, dict) and b.get("type") == "text"]
            if texts:
                return " ".join(texts)
    return ""


def _guess_field(phrase: str) -> str | None:
    normalized = phrase.strip().lower().replace(" ", "_")
    aliases = {
        "planting_date": "diaries.planting_date",
        "planting": "diaries.planting_date",
        "straw_management_date": "diaries.straw_management_date",
        "straw_management": "diaries.straw_management_date",
        "harvest_date": "diaries.harvest_date",
        "harvest": "diaries.harvest_date",
    }
    return aliases.get(normalized)
