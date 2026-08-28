from __future__ import annotations

from app.components.state import field_season_readiness_df, results_df
from copilot.models import (
    RuleIssueCount,
    TopValidationIssuesInput,
    TopValidationIssuesOutput,
    ValidationSummaryInput,
    ValidationSummaryOutput,
)
from copilot.tool_registry import CopilotToolRegistry
from copilot.tools._common import resolve_run_id, rule_issue_counts


def get_validation_summary(season_id: str | None, validation_run_id: str | None) -> ValidationSummaryOutput:
    run_id = resolve_run_id(validation_run_id)
    readiness = field_season_readiness_df(run_id)
    detail = results_df(run_id)
    if season_id:
        readiness = readiness[readiness["season_id"] == season_id]
        detail = detail[detail["season_id"] == season_id]

    total = len(readiness)
    top = rule_issue_counts(detail, total, result=None, limit=5)
    return ValidationSummaryOutput(
        validation_run_id=run_id,
        total_field_seasons=total,
        ready_count=int((readiness["readiness"] == "READY").sum()) if total else 0,
        review_required_count=int((readiness["readiness"] == "NEEDS_REVIEW").sum()) if total else 0,
        validation_failed_count=int((readiness["readiness"] == "FAILED").sum()) if total else 0,
        top_issues=[RuleIssueCount(**t) for t in top],
    )


def get_top_validation_issues(
    season_id: str | None, validation_run_id: str | None, result: str | None, limit: int
) -> TopValidationIssuesOutput:
    run_id = resolve_run_id(validation_run_id)
    readiness = field_season_readiness_df(run_id)
    detail = results_df(run_id)
    if season_id:
        readiness = readiness[readiness["season_id"] == season_id]
        detail = detail[detail["season_id"] == season_id]
    issues = rule_issue_counts(detail, len(readiness), result=result, limit=limit)
    return TopValidationIssuesOutput(issues=[RuleIssueCount(**i) for i in issues])


def register(registry: CopilotToolRegistry) -> None:
    registry.register(
        "get_validation_summary",
        "Summary statistics (READY/REVIEW_REQUIRED/VALIDATION_FAILED counts, total field-seasons, "
        "top issues) for a validation run or season. Defaults to the latest run if validation_run_id is omitted.",
        ValidationSummaryInput,
        ValidationSummaryOutput,
        get_validation_summary,
    )
    registry.register(
        "get_top_validation_issues",
        "The rules contributing the most FAIL/REVIEW results, ranked by affected field-season count, "
        "with each rule's share of the total. Optionally filter to one result type (FAIL or REVIEW).",
        TopValidationIssuesInput,
        TopValidationIssuesOutput,
        get_top_validation_issues,
    )
