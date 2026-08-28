from __future__ import annotations

import json

from app.components.state import (
    field_season_readiness_df,
    field_source_records,
    results_df,
    SOURCE_RECORD_TABLES,
)
from copilot.models import (
    FieldFinding,
    FieldFindingsInput,
    FieldFindingsOutput,
    FieldSourceRecordsInput,
    FieldSourceRecordsOutput,
    FieldValidationSummaryInput,
    FieldValidationSummaryOutput,
)
from copilot.tool_registry import CopilotToolRegistry
from copilot.tools._common import resolve_run_id, rules_lookup


def get_field_validation_summary(
    lot_id: str, season_id: str, validation_run_id: str | None
) -> FieldValidationSummaryOutput:
    run_id = resolve_run_id(validation_run_id)
    readiness = field_season_readiness_df(run_id)
    row = readiness[(readiness["lot_id"] == lot_id) & (readiness["season_id"] == season_id)]
    if row.empty:
        return FieldValidationSummaryOutput(found=False, lot_id=lot_id, season_id=season_id)

    r = row.iloc[0]
    primary_issue = r["fail_rule_ids"] or r["review_rule_ids"] or None
    detail = results_df(run_id)
    applicable = detail[
        (detail["lot_id"] == lot_id) & (detail["season_id"] == season_id) & (detail["result"] != "NOT_APPLICABLE")
    ]
    return FieldValidationSummaryOutput(
        found=True,
        lot_id=lot_id,
        season_id=season_id,
        readiness=r["readiness"],
        fail_count=int(r["fail_count"]),
        review_count=int(r["review_count"]),
        primary_issue=primary_issue,
        applicable_rule_count=len(applicable),
    )


def get_field_findings(
    lot_id: str, season_id: str, validation_run_id: str | None, result: str | None
) -> FieldFindingsOutput:
    run_id = resolve_run_id(validation_run_id)
    detail = results_df(run_id)
    rows = detail[(detail["lot_id"] == lot_id) & (detail["season_id"] == season_id)]
    if result:
        rows = rows[rows["result"] == result]
    if rows.empty:
        found = not detail[(detail["lot_id"] == lot_id) & (detail["season_id"] == season_id)].empty
        return FieldFindingsOutput(found=found, lot_id=lot_id, season_id=season_id, findings=[])

    rules = rules_lookup()
    findings = [
        FieldFinding(
            rule_id=r["rule_id"],
            rule_name=rules[r["rule_id"]].name if r["rule_id"] in rules else None,
            result=r["result"],
            reason=r["reason"],
            observations=json.loads(r["observations"]) if r["observations"] else {},
            missing_inputs=json.loads(r["missing_inputs"]) if r["missing_inputs"] else [],
        )
        for _, r in rows.sort_values("rule_id").iterrows()
    ]
    return FieldFindingsOutput(found=True, lot_id=lot_id, season_id=season_id, findings=findings)


def get_field_source_records(lot_id: str, season_id: str, table: str) -> FieldSourceRecordsOutput:
    if table not in SOURCE_RECORD_TABLES:
        return FieldSourceRecordsOutput(found=False, lot_id=lot_id, season_id=season_id, table=table)
    records = field_source_records(lot_id, season_id, table)
    return FieldSourceRecordsOutput(
        found=bool(records), lot_id=lot_id, season_id=season_id, table=table, records=records
    )


def register(registry: CopilotToolRegistry) -> None:
    registry.register(
        "get_field_validation_summary",
        "Overall readiness (READY/NEEDS_REVIEW/FAILED) for one field-season, plus counts of FAIL/REVIEW "
        "rules and the primary issue. Use this before get_field_findings to check a field-season exists.",
        FieldValidationSummaryInput,
        FieldValidationSummaryOutput,
        get_field_validation_summary,
    )
    registry.register(
        "get_field_findings",
        "Detailed per-rule findings for one field-season: rule, result, deterministic reason, observed "
        "values, and any missing data driving a REVIEW result. Optionally filter to one result type.",
        FieldFindingsInput,
        FieldFindingsOutput,
        get_field_findings,
    )
    registry.register(
        "get_field_source_records",
        "Raw underlying records for one field-season, to drill down beyond a rule's PASS/FAIL/REVIEW "
        "verdict into the actual values behind it - e.g. every fertilizer_applications row (applied_date, "
        "applied_amount_kg, in application order) for a field flagged by C9, or the diaries/photos rows "
        "behind another rule. table must be one of 'fertilizer_applications', 'diaries', 'photos'.",
        FieldSourceRecordsInput,
        FieldSourceRecordsOutput,
        get_field_source_records,
    )
