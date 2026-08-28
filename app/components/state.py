"""Shared Streamlit resources: cached data/store connections and the Run
Validation workflow. Kept out of the LLM path entirely - the Data page and
Run Validation never touch the agents.
"""

from __future__ import annotations

import re
import uuid
from datetime import date, datetime

import duckdb
import pandas as pd
import streamlit as st

import validation.operators  # noqa: F401  (registers all operators)
from adapters import csv_adapter
from agents.providers.anthropic_provider import AnthropicProvider, is_configured
from agents.providers.mock_provider import MockProvider
from agents.rule_authoring import RuleAuthoringAgent
from catalog.loader import known_fields
from persistence import duckdb_store
from validation.dsl.loader import delete_rule_file, load_all_rules, save_rule_file
from validation.dsl.validate import RuleValidationError, validate_rule
from validation.engine import run_batch
from validation.models import RuleStatus


@st.cache_resource
def get_data_connection() -> duckdb.DuckDBPyConnection:
    con = csv_adapter.get_connection()
    csv_adapter.load_all(con)
    return con


@st.cache_resource
def get_store_connection() -> duckdb.DuckDBPyConnection:
    return duckdb_store.get_connection()


def get_rules(validate: bool = True):
    return load_all_rules(validate=validate)


def get_rule_authoring_agent() -> RuleAuthoringAgent | None:
    if not is_configured():
        return None
    return RuleAuthoringAgent(AnthropicProvider())


def get_custom_rules():
    """Agent-authored rules saved via the Rules page (any status), excluding
    the static C1-C9 rules even though a prior Run Data Validation may have
    also persisted those into the same store (see run_validation)."""
    static_ids = {r.rule_id for r in get_rules(validate=False)}
    all_stored = duckdb_store.load_all_rules(get_store_connection())
    return [r for r in all_stored if r.rule_id not in static_ids]


def next_custom_rule_id() -> str:
    """The next 'C<n>' id after the highest currently in use, across both
    the static rule pack and any already-saved custom rules - so a newly
    authored rule slots in right after the last one in the list instead of
    getting an opaque CUSTOM_<hash> id."""
    static_ids = [r.rule_id for r in get_rules(validate=False)]
    custom_ids = [r.rule_id for r in duckdb_store.load_all_rules(get_store_connection())]
    highest = 0
    for rule_id in static_ids + custom_ids:
        match = re.fullmatch(r"C(\d+)", rule_id)
        if match:
            highest = max(highest, int(match.group(1)))
    return f"C{highest + 1}"


def delete_custom_rule(rule_id: str) -> None:
    duckdb_store.delete_rule(get_store_connection(), rule_id)


def delete_static_rule(rule_id: str) -> None:
    """Deletes a base rule pack rule (rules/<rule_id>.yaml) - irreversible
    outside of git. Also purges any copy of it persisted into the store by
    a prior Run Data Validation, so it doesn't linger there as stale data."""
    delete_rule_file(rule_id)
    duckdb_store.delete_rule(get_store_connection(), rule_id)


def promote_custom_rule(rule_id: str) -> None:
    """Writes a tested/saved custom rule out as a permanent rules/<id>.yaml
    file - the workaround for the DuckDB store possibly not surviving a
    redeploy (see README): a user sends you a rule, you build/test/save it
    here, then promote it so it ships with the app's code from then on.
    Re-validates before writing so a bad definition can't get promoted and
    then crash every future `get_rules()` call (used with validate=True
    elsewhere, e.g. Run Data Validation)."""
    rule = next((r for r in get_custom_rules() if r.rule_id == rule_id), None)
    if rule is None:
        raise ValueError(f"no custom rule found with id {rule_id!r}")
    promoted = rule.model_copy(
        update={"version": 1, "status": RuleStatus.ACTIVE, "activated_at": datetime.utcnow().isoformat()}
    )
    errors = validate_rule(promoted, known_fields())
    if errors:
        raise RuleValidationError(errors)
    save_rule_file(promoted)


def run_validation(season_ids: list[str] | None = None) -> str:
    """`season_ids`, if given, restricts the run to those seasons (e.g.
    ["3"] for Dry Crop 2025 only); None runs every loaded season."""
    data_con = get_data_connection()
    store_con = get_store_connection()
    static_rules = get_rules()

    for rule in static_rules:
        duckdb_store.save_rule_version(store_con, rule)

    # Merge in any custom rules activated via the Rules page (persisted in
    # the store, not in rules/*.yaml) so Run Validation picks them up too -
    # static rules win on rule_id collisions since they were just re-saved.
    combined_rules = {r.rule_id: r for r in duckdb_store.load_active_rules(store_con)}
    combined_rules.update({r.rule_id: r for r in static_rules})
    rules = list(combined_rules.values())

    validation_run_id = f"run-{uuid.uuid4().hex[:12]}"
    started_at = datetime.utcnow()
    results = run_batch(data_con, rules, validation_run_id, evaluated_at=started_at, season_ids=season_ids)
    finished_at = datetime.utcnow()

    duckdb_store.save_results(
        store_con, validation_run_id, [r.rule_id for r in rules], results, started_at, finished_at
    )
    return validation_run_id


def latest_run_id() -> str | None:
    return duckdb_store.latest_run_id(get_store_connection())


@st.cache_data
def results_df(run_id: str | None = None) -> pd.DataFrame:
    store_con = get_store_connection()
    run_id = run_id or latest_run_id()
    if run_id is None:
        return pd.DataFrame()
    return store_con.execute(
        "SELECT * FROM validation_results WHERE validation_run_id = ?", [run_id]
    ).fetchdf()


@st.cache_data
def field_season_readiness_df(run_id: str | None = None) -> pd.DataFrame:
    """One row per lot_id/season_id: readiness + fail/review rule id lists.

    Aggregated in DuckDB SQL, not pandas groupby().apply() - the latter
    calls a Python function per group (~32k groups here) and was ~40x
    slower (12s vs 0.3s on the full dataset), enough to look "stuck" or
    empty in the UI while it silently churned through every rerun.
    """
    store_con = get_store_connection()
    run_id = run_id or latest_run_id()
    if run_id is None:
        return pd.DataFrame()
    return store_con.execute(
        """
        SELECT
            lot_id,
            season_id,
            CASE
                WHEN SUM(CASE WHEN result = 'FAIL' THEN 1 ELSE 0 END) > 0 THEN 'FAILED'
                WHEN SUM(CASE WHEN result = 'REVIEW' THEN 1 ELSE 0 END) > 0 THEN 'NEEDS_REVIEW'
                ELSE 'READY'
            END AS readiness,
            COALESCE(string_agg(CASE WHEN result = 'FAIL' THEN rule_id END, ',' ORDER BY rule_id), '') AS fail_rule_ids,
            COALESCE(string_agg(CASE WHEN result = 'REVIEW' THEN rule_id END, ',' ORDER BY rule_id), '') AS review_rule_ids,
            SUM(CASE WHEN result = 'FAIL' THEN 1 ELSE 0 END) AS fail_count,
            SUM(CASE WHEN result = 'REVIEW' THEN 1 ELSE 0 END) AS review_count,
            ? AS validation_run_id
        FROM validation_results
        WHERE validation_run_id = ?
        GROUP BY lot_id, season_id
        """,
        [run_id, run_id],
    ).fetchdf()


@st.cache_data
def lots_attributes_df() -> pd.DataFrame:
    """lot_id/season_id -> the lot-identifying attributes Field Review
    filters/displays on (field name, TSAG, IA, RIS) instead of raw
    field_id. season_id is cast to VARCHAR to match validation_results'
    (and readiness_df's) string season_id for joining."""
    con = get_data_connection()
    return con.execute(
        """
        SELECT
            lot_id,
            CAST(season_id AS VARCHAR) AS season_id,
            unique_name AS field_name,
            tsag,
            irrigators_association AS ia,
            irrigation_system AS ris
        FROM lots
        """
    ).fetchdf()


# The raw source tables a field-season's records can be drilled into - the
# same ones the rule engine reads (validation/engine.py) and which have
# already been loaded through the PII allowlist (adapters/pii_policy.py), so
# every column on every one of these tables is safe to display/return as-is.
SOURCE_RECORD_TABLES = {
    "fertilizer_applications": "application_id",
    "diaries": "diary_id",
    "photos": "photo_id",
}


def field_source_records(lot_id: str, season_id: str, table: str) -> list[dict]:
    """Raw rows from one source table for one field-season, in the same
    order the rule engine consumes them - used both by Field Review's detail
    expander (to show the actual values behind a FAIL/REVIEW) and by the
    Copilot's get_field_source_records tool."""
    order_field = SOURCE_RECORD_TABLES.get(table)
    if order_field is None:
        return []
    con = get_data_connection()
    rows = con.execute(
        f"SELECT * FROM {table} WHERE lot_id = ? AND CAST(season_id AS VARCHAR) = ? ORDER BY {order_field}",
        [lot_id, season_id],
    ).fetchall()
    columns = [c[0] for c in con.description]
    return [
        {
            col: (value.isoformat() if isinstance(value, (date, datetime)) else value)
            for col, value in zip(columns, row)
        }
        for row in rows
    ]
