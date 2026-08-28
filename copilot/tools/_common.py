"""Shared helpers for Copilot tools - not a tool itself. Thin wrappers
around app.components.state / persistence.duckdb_store so tool modules stay
short; no query logic is duplicated here that isn't already used elsewhere
in the app.
"""

from __future__ import annotations

import pandas as pd

from app.components.state import get_custom_rules, get_rules, latest_run_id
from validation.models import Rule


class NoValidationRunError(Exception):
    """No validation run exists yet for this store - the Copilot should
    tell the user to run validation first, not crash."""


def resolve_run_id(validation_run_id: str | None) -> str:
    run_id = validation_run_id or latest_run_id()
    if run_id is None:
        raise NoValidationRunError("No validation run exists yet - run one from Data & Setup first.")
    return run_id


def rules_lookup() -> dict[str, Rule]:
    """rule_id -> Rule, static C1-C9 plus any custom (agent-authored) rules,
    matching the same combined view Field Review's detail expander uses."""
    combined: dict[str, Rule] = {r.rule_id: r for r in get_rules(validate=False)}
    combined.update({r.rule_id: r for r in get_custom_rules()})
    return combined


def rule_issue_counts(detail_df: pd.DataFrame, total_field_seasons: int, result: str | None, limit: int) -> list[dict]:
    """Aggregates validation_results rows into per-rule issue counts. If
    `result` is given, restricts to that result; otherwise counts FAIL and
    REVIEW (the two "issue" outcomes) together, split by rule+result."""
    rules = rules_lookup()
    df = detail_df
    if result:
        df = df[df["result"] == result]
    else:
        df = df[df["result"].isin(["FAIL", "REVIEW"])]
    if df.empty:
        return []
    counts = df.groupby(["rule_id", "result"]).size().reset_index(name="field_season_count")
    counts = counts.sort_values("field_season_count", ascending=False).head(limit)
    denom = total_field_seasons or 1
    return [
        {
            "rule_id": row["rule_id"],
            "rule_name": rules[row["rule_id"]].name if row["rule_id"] in rules else row["rule_id"],
            "result": row["result"],
            "field_season_count": int(row["field_season_count"]),
            "percentage": round(100 * row["field_season_count"] / denom, 1),
        }
        for _, row in counts.iterrows()
    ]
