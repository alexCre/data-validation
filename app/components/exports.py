"""Field Summary / Detailed Validation CSV export builders - the single
implementation used by both the Field Review page and the Copilot's
export_validation_csv tool, so export business logic is never duplicated.
"""

from __future__ import annotations

import pandas as pd


def field_summary_export_df(readiness_df: pd.DataFrame, season_labels: dict[str, str]) -> pd.DataFrame:
    """One row per field-season: identity, readiness, and the rule ids
    behind any FAIL/REVIEW. `readiness_df` must already carry field_name/
    tsag/ia/ris (see app.components.state.lots_attributes_df)."""
    if readiness_df.empty:
        return pd.DataFrame(
            columns=[
                "lot_id", "field_name", "tsag", "ia", "ris", "season_id", "season",
                "readiness", "failed_rule_ids", "review_rule_ids", "num_fail",
                "num_review", "primary_issue", "validation_run_id",
            ]
        )
    field_summary = readiness_df.rename(
        columns={"fail_rule_ids": "failed_rule_ids", "review_rule_ids": "review_rule_ids"}
    ).copy()
    field_summary["num_fail"] = field_summary["fail_count"]
    field_summary["num_review"] = field_summary["review_count"]
    field_summary["primary_issue"] = field_summary["failed_rule_ids"].where(
        field_summary["failed_rule_ids"] != "", field_summary["review_rule_ids"]
    )
    field_summary["season"] = field_summary["season_id"].map(lambda s: season_labels.get(s, s))
    return field_summary[
        [
            "lot_id", "field_name", "tsag", "ia", "ris", "season_id", "season",
            "readiness", "failed_rule_ids", "review_rule_ids", "num_fail",
            "num_review", "primary_issue", "validation_run_id",
        ]
    ]


def detailed_export_df(
    detail_df: pd.DataFrame, lots_attributes_df: pd.DataFrame, season_labels: dict[str, str]
) -> pd.DataFrame:
    """One row per field-season x rule, joined to field identity."""
    if detail_df.empty:
        return pd.DataFrame(
            columns=[
                "lot_id", "field_name", "tsag", "ia", "ris", "season_id", "season",
                "rule_id", "rule_version", "result", "reason", "observations",
                "validation_run_id", "evaluated_at",
            ]
        )
    detailed = detail_df.merge(lots_attributes_df, on=["lot_id", "season_id"], how="left")
    detailed["season"] = detailed["season_id"].map(lambda s: season_labels.get(s, s))
    return detailed[
        [
            "lot_id", "field_name", "tsag", "ia", "ris", "season_id", "season",
            "rule_id", "rule_version", "result", "reason", "observations",
            "validation_run_id", "evaluated_at",
        ]
    ]
