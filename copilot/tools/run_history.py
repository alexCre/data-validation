from __future__ import annotations

import pandas as pd

from app.components.state import field_season_readiness_df, get_store_connection, results_df
from copilot.models import (
    CompareValidationRunsInput,
    CompareValidationRunsOutput,
    RuleIssueCount,
    ValidationRunHistoryInput,
    ValidationRunHistoryOutput,
    ValidationRunSummary,
)
from copilot.tool_registry import CopilotToolRegistry
from copilot.tools._common import rules_lookup
from persistence import duckdb_store


def _rule_counts_by_result(detail_df: pd.DataFrame) -> dict[tuple[str, str], int]:
    if detail_df.empty:
        return {}
    counts = detail_df[detail_df["result"].isin(["FAIL", "REVIEW"])].groupby(["rule_id", "result"]).size()
    return {(rule_id, result): int(n) for (rule_id, result), n in counts.items()}


def compare_validation_runs(
    run_a: str, run_b: str, season_id: str | None, rule_id: str | None
) -> CompareValidationRunsOutput:
    readiness_a = field_season_readiness_df(run_a)
    readiness_b = field_season_readiness_df(run_b)
    if readiness_a.empty or readiness_b.empty:
        return CompareValidationRunsOutput(found=False, run_a=run_a, run_b=run_b)

    if season_id:
        readiness_a = readiness_a[readiness_a["season_id"] == season_id]
        readiness_b = readiness_b[readiness_b["season_id"] == season_id]

    def _counts(df: pd.DataFrame) -> dict[str, int]:
        return {
            "READY": int((df["readiness"] == "READY").sum()),
            "NEEDS_REVIEW": int((df["readiness"] == "NEEDS_REVIEW").sum()),
            "FAILED": int((df["readiness"] == "FAILED").sum()),
        }

    counts_a, counts_b = _counts(readiness_a), _counts(readiness_b)

    key_a = readiness_a.set_index(["lot_id", "season_id"])["readiness"]
    key_b = readiness_b.set_index(["lot_id", "season_id"])["readiness"]
    joined = key_a.to_frame("readiness_a").join(key_b.to_frame("readiness_b"), how="inner")
    newly_failing = int(((joined["readiness_a"] != "FAILED") & (joined["readiness_b"] == "FAILED")).sum())
    resolved = int(((joined["readiness_a"] == "FAILED") & (joined["readiness_b"] != "FAILED")).sum())

    detail_a = results_df(run_a)
    detail_b = results_df(run_b)
    if season_id:
        detail_a = detail_a[detail_a["season_id"] == season_id]
        detail_b = detail_b[detail_b["season_id"] == season_id]
    if rule_id:
        detail_a = detail_a[detail_a["rule_id"] == rule_id]
        detail_b = detail_b[detail_b["rule_id"] == rule_id]

    counts_by_rule_a = _rule_counts_by_result(detail_a)
    counts_by_rule_b = _rule_counts_by_result(detail_b)
    rules = rules_lookup()
    changes = []
    for key in set(counts_by_rule_a) | set(counts_by_rule_b):
        rid, result = key
        delta = counts_by_rule_b.get(key, 0) - counts_by_rule_a.get(key, 0)
        if delta == 0:
            continue
        changes.append((rid, result, delta))
    changes.sort(key=lambda c: abs(c[2]), reverse=True)
    top_changes = [
        RuleIssueCount(
            rule_id=rid,
            rule_name=rules[rid].name if rid in rules else rid,
            result=result,
            field_season_count=delta,
            percentage=0.0,
        )
        for rid, result, delta in changes[:5]
    ]

    return CompareValidationRunsOutput(
        found=True,
        run_a=run_a,
        run_b=run_b,
        ready_change=counts_b["READY"] - counts_a["READY"],
        review_required_change=counts_b["NEEDS_REVIEW"] - counts_a["NEEDS_REVIEW"],
        failed_change=counts_b["FAILED"] - counts_a["FAILED"],
        newly_failing_count=newly_failing,
        resolved_count=resolved,
        rules_with_biggest_change=top_changes,
    )


def get_validation_run_history(limit: int) -> ValidationRunHistoryOutput:
    runs = duckdb_store.list_runs(get_store_connection(), limit=limit)
    return ValidationRunHistoryOutput(
        runs=[
            ValidationRunSummary(
                validation_run_id=r["validation_run_id"],
                started_at=str(r["started_at"]),
                finished_at=str(r["finished_at"]),
                rule_count=r["rule_count"],
                field_season_count=r["field_season_count"],
                ready_count=r["ready_count"],
                review_required_count=r["review_count"],
                validation_failed_count=r["failed_count"],
                season_ids=r["season_ids"],
            )
            for r in runs
        ]
    )


def register(registry: CopilotToolRegistry) -> None:
    registry.register(
        "compare_validation_runs",
        "Compares two validation runs: change in READY/REVIEW_REQUIRED/VALIDATION_FAILED counts, how "
        "many field-seasons newly failed or got resolved, and which rules changed the most. Optionally "
        "restrict to one season or rule.",
        CompareValidationRunsInput,
        CompareValidationRunsOutput,
        compare_validation_runs,
    )
    registry.register(
        "get_validation_run_history",
        "Recent validation runs (most recent first) with timestamp, season(s), rule count, "
        "field-season count, and READY/REVIEW_REQUIRED/VALIDATION_FAILED counts.",
        ValidationRunHistoryInput,
        ValidationRunHistoryOutput,
        get_validation_run_history,
    )
