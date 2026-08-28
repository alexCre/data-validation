"""Typed input/output models for every Copilot tool. Kept separate from
agents.models (Rule Authoring / Capability Extension's models) since these
describe a different boundary: structured validation *query* results, not
LLM-compiled rule definitions.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

# --- shared building blocks ---


class RuleIssueCount(BaseModel):
    rule_id: str
    rule_name: str
    result: str
    field_season_count: int
    percentage: float


class FieldRef(BaseModel):
    lot_id: str
    season_id: str
    field_name: str | None = None


# --- Tool 1: get_validation_summary ---


class ValidationSummaryInput(BaseModel):
    season_id: str | None = None
    validation_run_id: str | None = None


class ValidationSummaryOutput(BaseModel):
    validation_run_id: str
    total_field_seasons: int
    ready_count: int
    review_required_count: int
    validation_failed_count: int
    top_issues: list[RuleIssueCount] = Field(default_factory=list)


# --- Tool 2: get_top_validation_issues ---


class TopValidationIssuesInput(BaseModel):
    season_id: str | None = None
    validation_run_id: str | None = None
    result: str | None = Field(default=None, description="Filter to one result: PASS, FAIL, REVIEW, NOT_APPLICABLE")
    limit: int = Field(default=10, ge=1, le=50)


class TopValidationIssuesOutput(BaseModel):
    issues: list[RuleIssueCount]


# --- Tool 3: get_validation_results ---


class ValidationResultsInput(BaseModel):
    season_id: str | None = None
    rule_id: str | None = Field(
        default=None, description="A rule id like 'C6' or 'C9' - always the letter C followed by digits."
    )
    result: str | None = None
    lot_id: str | None = Field(
        default=None,
        description="A field/lot identifier - a plain number (e.g. '123437'), never starting with 'C' "
        "(a 'C<digits>' reference is a rule_id, not a lot_id).",
    )
    validation_run_id: str | None = None
    limit: int = Field(default=20, ge=1, le=200)
    offset: int = Field(default=0, ge=0)


class ValidationResultRow(BaseModel):
    lot_id: str
    season_id: str
    rule_id: str
    result: str
    reason: str


class ValidationResultsOutput(BaseModel):
    total_matching: int
    returned: int
    offset: int
    rows: list[ValidationResultRow]
    truncated: bool


# --- Tool 4: get_field_validation_summary ---


class FieldValidationSummaryInput(BaseModel):
    lot_id: str = Field(description="A plain field/lot identifier number, e.g. '123437' - never a rule id.")
    season_id: str
    validation_run_id: str | None = None


class FieldValidationSummaryOutput(BaseModel):
    found: bool
    lot_id: str
    season_id: str
    readiness: str | None = None
    fail_count: int = 0
    review_count: int = 0
    primary_issue: str | None = None
    applicable_rule_count: int = 0


# --- Tool 5: get_field_findings ---


class FieldFindingsInput(BaseModel):
    lot_id: str = Field(description="A plain field/lot identifier number, e.g. '123437' - never a rule id.")
    season_id: str
    validation_run_id: str | None = None
    result: str | None = None


class FieldFinding(BaseModel):
    rule_id: str
    rule_name: str | None = None
    result: str
    reason: str
    observations: dict[str, Any] = Field(default_factory=dict)
    missing_inputs: list[str] = Field(default_factory=list)


class FieldFindingsOutput(BaseModel):
    found: bool
    lot_id: str
    season_id: str
    findings: list[FieldFinding] = Field(default_factory=list)


# --- Tool 6: get_rule_details ---


class RuleDetailsInput(BaseModel):
    rule_id: str


class RuleDetailsOutput(BaseModel):
    found: bool
    rule_id: str
    name: str | None = None
    description: str | None = None
    version: int | None = None
    status: str | None = None
    missing_data_policy: str | None = None
    required_inputs: list[str] = Field(default_factory=list)


# --- Tool 7: compare_validation_runs ---


class CompareValidationRunsInput(BaseModel):
    run_a: str
    run_b: str
    season_id: str | None = None
    rule_id: str | None = None


class CompareValidationRunsOutput(BaseModel):
    found: bool
    run_a: str
    run_b: str
    ready_change: int = 0
    review_required_change: int = 0
    failed_change: int = 0
    newly_failing_count: int = 0
    resolved_count: int = 0
    rules_with_biggest_change: list[RuleIssueCount] = Field(default_factory=list)


# --- Tool 8: export_validation_csv ---


class ExportValidationCsvInput(BaseModel):
    mode: str = Field(description="FIELD_SUMMARY or DETAILED")
    season_id: str | None = None
    rule_id: str | None = None
    result: str | None = None
    validation_run_id: str | None = None


class ExportValidationCsvOutput(BaseModel):
    row_count: int
    file_path: str
    file_name: str


# --- Tool 9: request_new_rule ---


class RequestNewRuleInput(BaseModel):
    rule_text: str


class RequestNewRuleOutput(BaseModel):
    status: str
    request_id: str | None = Field(
        default=None, description="Internal reference for the UI hand-off - not meaningful to the model."
    )
    interpretation: str | None = None
    required_inputs: list[str] = Field(default_factory=list)
    selected_operators: list[str] = Field(default_factory=list)
    assumptions: list[str] = Field(default_factory=list)
    pass_criteria: str | None = None
    fail_criteria: str | None = None
    review_criteria: str | None = None
    clarification_questions: list[str] = Field(default_factory=list)
    missing_capabilities: list[str] = Field(default_factory=list)
    proposed_operator_names: list[str] = Field(default_factory=list)


# --- Tool 11: get_field_source_records ---


class FieldSourceRecordsInput(BaseModel):
    lot_id: str = Field(description="A plain field/lot identifier number, e.g. '123437' - never a rule id.")
    season_id: str
    table: str = Field(
        description="Which raw source to drill into: 'fertilizer_applications', 'diaries', or 'photos'."
    )


class FieldSourceRecordsOutput(BaseModel):
    found: bool
    lot_id: str
    season_id: str
    table: str
    records: list[dict[str, Any]] = Field(
        default_factory=list,
        description="Raw rows for this field-season, in the same order the rule engine consumes them.",
    )


# --- Tool 10: get_validation_run_history ---


class ValidationRunHistoryInput(BaseModel):
    limit: int = Field(default=10, ge=1, le=50)


class ValidationRunSummary(BaseModel):
    validation_run_id: str
    started_at: str
    finished_at: str
    rule_count: int
    field_season_count: int
    ready_count: int
    review_required_count: int
    validation_failed_count: int
    season_ids: list[str] = Field(default_factory=list)


class ValidationRunHistoryOutput(BaseModel):
    runs: list[ValidationRunSummary]
