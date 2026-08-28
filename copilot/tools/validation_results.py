from __future__ import annotations

from app.components.state import results_df
from copilot.models import ValidationResultRow, ValidationResultsInput, ValidationResultsOutput
from copilot.tool_registry import CopilotToolRegistry
from copilot.tools._common import resolve_run_id


def get_validation_results(
    season_id: str | None,
    rule_id: str | None,
    result: str | None,
    lot_id: str | None,
    validation_run_id: str | None,
    limit: int,
    offset: int,
) -> ValidationResultsOutput:
    run_id = resolve_run_id(validation_run_id)
    df = results_df(run_id)
    if season_id:
        df = df[df["season_id"] == season_id]
    if rule_id:
        df = df[df["rule_id"] == rule_id]
    if result:
        df = df[df["result"] == result]
    if lot_id:
        df = df[df["lot_id"] == lot_id]

    total = len(df)
    page = df.iloc[offset : offset + limit]
    rows = [
        ValidationResultRow(
            lot_id=r["lot_id"], season_id=r["season_id"], rule_id=r["rule_id"], result=r["result"], reason=r["reason"]
        )
        for _, r in page.iterrows()
    ]
    return ValidationResultsOutput(
        total_matching=total,
        returned=len(rows),
        offset=offset,
        rows=rows,
        truncated=(offset + len(rows)) < total,
    )


def register(registry: CopilotToolRegistry) -> None:
    registry.register(
        "get_validation_results",
        "Retrieve filtered validation findings (one row per field-season x rule). Filters: season_id, "
        "rule_id, result (PASS/FAIL/REVIEW/NOT_APPLICABLE), lot_id, validation_run_id. Paginated - "
        "never returns more than `limit` (max 200) rows at once; use offset for more, or "
        "export_validation_csv for the full set.",
        ValidationResultsInput,
        ValidationResultsOutput,
        get_validation_results,
    )
