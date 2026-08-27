from __future__ import annotations

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field, model_validator

from validation.models import ExpressionNode, MissingDataPolicy


class CompilationStatus(StrEnum):
    COMPILED = "COMPILED"
    NEEDS_CLARIFICATION = "NEEDS_CLARIFICATION"
    UNSUPPORTED_CAPABILITY = "UNSUPPORTED_CAPABILITY"


class RuleCompilationResult(BaseModel):
    status: CompilationStatus

    # COMPILED - interpretation and the three outcome-criteria fields are
    # required (see _compiled_result_is_explained below) so a user is never
    # asked to test/save a rule they haven't actually had explained to them.
    expression: ExpressionNode | None = None
    interpretation: str | None = None
    required_inputs: list[str] = Field(default_factory=list)
    selected_operators: list[str] = Field(default_factory=list)
    assumptions: list[str] = Field(default_factory=list)
    pass_criteria: str | None = None
    fail_criteria: str | None = None
    review_criteria: str | None = None
    suggested_missing_data_policy: MissingDataPolicy | None = None

    # NEEDS_CLARIFICATION
    understood_portion: str | None = None
    clarification_questions: list[str] = Field(default_factory=list)
    ambiguity_explanation: str | None = None

    # UNSUPPORTED_CAPABILITY
    understood_goal: str | None = None
    supported_parts: list[str] = Field(default_factory=list)
    missing_capabilities: list[str] = Field(default_factory=list)
    proposed_operator_names: list[str] = Field(default_factory=list)
    insufficiency_reason: str | None = None

    @model_validator(mode="after")
    def _compiled_result_is_explained(self) -> "RuleCompilationResult":
        if self.status != CompilationStatus.COMPILED:
            return self
        missing = [
            field_name
            for field_name, value in (
                ("interpretation", self.interpretation),
                ("pass_criteria", self.pass_criteria),
                ("fail_criteria", self.fail_criteria),
                ("review_criteria", self.review_criteria),
            )
            if not value
        ]
        if missing:
            raise ValueError(
                "COMPILED result is missing required plain-language explanation "
                f"field(s): {', '.join(missing)}"
            )
        return self


class CapabilityGapSpec(BaseModel):
    missing_capability: str
    proposed_operator_name: str
    purpose: str
    reusable_semantics: str
    input_contract: dict[str, str]
    output_contract: str
    configuration_parameters: dict[str, str] = Field(default_factory=dict)
    edge_cases: list[str] = Field(default_factory=list)
    failure_behavior: str
    suggested_unit_tests: list[str] = Field(default_factory=list)
    example_rules: list[str] = Field(default_factory=list)


class GeneratedOperatorDraft(BaseModel):
    operator_name: str
    implementation_code: str
    test_code: str
    metadata: dict[str, Any] = Field(default_factory=dict)
    notes: str | None = None
