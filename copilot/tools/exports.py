"""export_validation_csv - reuses app.components.exports (the same builders
Field Review's download buttons use) so export business logic lives in
exactly one place. Writes to a local temp file and returns its path/row
count only - the CSV bytes never go back through the LLM (see
agents/validation_copilot.py's max tool-result size handling)."""

from __future__ import annotations

import tempfile
import uuid
from pathlib import Path

from app.components.exports import detailed_export_df, field_summary_export_df
from app.components.state import field_season_readiness_df, lots_attributes_df, results_df
from catalog.loader import season_labels
from copilot.models import ExportValidationCsvInput, ExportValidationCsvOutput
from copilot.tool_registry import CopilotToolRegistry
from copilot.tools._common import resolve_run_id

EXPORT_DIR = Path(tempfile.gettempdir()) / "dmrv_copilot_exports"


def export_validation_csv(
    mode: str, season_id: str | None, rule_id: str | None, result: str | None, validation_run_id: str | None
) -> ExportValidationCsvOutput:
    run_id = resolve_run_id(validation_run_id)
    labels = season_labels()
    mode_upper = mode.upper()

    if mode_upper == "FIELD_SUMMARY":
        readiness = field_season_readiness_df(run_id).merge(
            lots_attributes_df(), on=["lot_id", "season_id"], how="left"
        )
        if season_id:
            readiness = readiness[readiness["season_id"] == season_id]
        if rule_id:
            readiness = readiness[
                readiness["fail_rule_ids"].str.contains(rule_id, na=False)
                | readiness["review_rule_ids"].str.contains(rule_id, na=False)
            ]
        if result == "FAIL":
            readiness = readiness[readiness["fail_count"] > 0]
        elif result == "REVIEW":
            readiness = readiness[readiness["review_count"] > 0]
        df = field_summary_export_df(readiness, labels)
        file_prefix = "field_summary"
    elif mode_upper == "DETAILED":
        detail = results_df(run_id)
        if season_id:
            detail = detail[detail["season_id"] == season_id]
        if rule_id:
            detail = detail[detail["rule_id"] == rule_id]
        if result:
            detail = detail[detail["result"] == result]
        df = detailed_export_df(detail, lots_attributes_df(), labels)
        file_prefix = "detailed_validation"
    else:
        raise ValueError(f"mode must be FIELD_SUMMARY or DETAILED, got {mode!r}")

    EXPORT_DIR.mkdir(parents=True, exist_ok=True)
    file_name = f"{file_prefix}_{run_id}_{uuid.uuid4().hex[:8]}.csv"
    file_path = EXPORT_DIR / file_name
    df.to_csv(file_path, index=False)
    return ExportValidationCsvOutput(row_count=len(df), file_path=str(file_path), file_name=file_name)


def register(registry: CopilotToolRegistry) -> None:
    registry.register(
        "export_validation_csv",
        "Exports validation results to a CSV file (FIELD_SUMMARY: one row per field-season; DETAILED: "
        "one row per field-season x rule), using the same export logic as Field Review's download "
        "buttons. Returns a row count and a local file reference for the UI to offer as a download - "
        "never the CSV content itself.",
        ExportValidationCsvInput,
        ExportValidationCsvOutput,
        export_validation_csv,
    )
