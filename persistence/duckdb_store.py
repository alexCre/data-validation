"""Persists rules, rule versions, validation runs, and validation results in
a local DuckDB file. CSV source data is loaded separately (adapters) into
the same connection so results can be joined against lot/diary/photo data
for the Streamlit app.
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

import duckdb
import pandas as pd

from validation.models import Rule
from validation.result_models import ValidationResult

DEFAULT_DB_PATH = Path(__file__).resolve().parents[1] / "dmrv_validation.duckdb"

_SCHEMA = """
CREATE TABLE IF NOT EXISTS rule_versions (
    rule_id VARCHAR,
    version INTEGER,
    name VARCHAR,
    description VARCHAR,
    status VARCHAR,
    source_text VARCHAR,
    definition JSON,
    created_at TIMESTAMP,
    activated_at TIMESTAMP,
    PRIMARY KEY (rule_id, version)
);

CREATE TABLE IF NOT EXISTS validation_runs (
    validation_run_id VARCHAR PRIMARY KEY,
    started_at TIMESTAMP,
    finished_at TIMESTAMP,
    rule_ids JSON,
    row_count INTEGER
);

CREATE TABLE IF NOT EXISTS validation_results (
    validation_run_id VARCHAR,
    lot_id VARCHAR,
    season_id VARCHAR,
    rule_id VARCHAR,
    rule_version INTEGER,
    result VARCHAR,
    reason VARCHAR,
    observations JSON,
    missing_inputs JSON,
    evaluated_at TIMESTAMP
);

CREATE TABLE IF NOT EXISTS capability_gaps (
    gap_id VARCHAR PRIMARY KEY,
    rule_text VARCHAR,
    missing_capability VARCHAR,
    proposed_operator_name VARCHAR,
    spec JSON,
    created_at TIMESTAMP
);

CREATE TABLE IF NOT EXISTS generated_draft_metadata (
    operator_name VARCHAR PRIMARY KEY,
    gap_id VARCHAR,
    path VARCHAR,
    created_at TIMESTAMP,
    promoted_at TIMESTAMP
);
"""


def get_connection(db_path: Path | str = DEFAULT_DB_PATH) -> duckdb.DuckDBPyConnection:
    con = duckdb.connect(str(db_path))
    con.execute(_SCHEMA)
    # Migration for DBs created before missing_inputs existed.
    con.execute("ALTER TABLE validation_results ADD COLUMN IF NOT EXISTS missing_inputs JSON")
    # Migration for DBs created before severity was dropped.
    con.execute("ALTER TABLE rule_versions DROP COLUMN IF EXISTS severity")
    con.execute("ALTER TABLE validation_results DROP COLUMN IF EXISTS severity")
    return con


def save_rule_version(con: duckdb.DuckDBPyConnection, rule: Rule) -> None:
    con.execute(
        """
        INSERT INTO rule_versions
            (rule_id, version, name, description, status, source_text, definition, created_at, activated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT (rule_id, version) DO UPDATE SET
            name = excluded.name,
            description = excluded.description,
            status = excluded.status,
            definition = excluded.definition,
            activated_at = excluded.activated_at
        """,
        [
            rule.rule_id,
            rule.version,
            rule.name,
            rule.description,
            rule.status.value,
            rule.source_text,
            rule.model_dump_json(),
            rule.created_at or datetime.utcnow().isoformat(),
            rule.activated_at,
        ],
    )


def save_results(
    con: duckdb.DuckDBPyConnection,
    validation_run_id: str,
    rule_ids: list[str],
    results: list[ValidationResult],
    started_at: datetime,
    finished_at: datetime,
) -> None:
    con.execute(
        "INSERT INTO validation_runs VALUES (?, ?, ?, ?, ?)",
        [validation_run_id, started_at, finished_at, json.dumps(rule_ids), len(results)],
    )
    # Bulk-load via a registered in-memory table rather than executemany,
    # which serializes one parameterized INSERT per row - too slow for
    # ~350k+ results (11 rules x tens of thousands of field-seasons).
    results_df = pd.DataFrame(
        {
            "validation_run_id": [r.validation_run_id for r in results],
            "lot_id": [r.lot_id for r in results],
            "season_id": [r.season_id for r in results],
            "rule_id": [r.rule_id for r in results],
            "rule_version": [r.rule_version for r in results],
            "result": [r.result.value for r in results],
            "reason": [r.reason for r in results],
            "observations": [json.dumps(r.observations, default=str) for r in results],
            "missing_inputs": [json.dumps(r.missing_inputs) for r in results],
            "evaluated_at": [r.evaluated_at for r in results],
        }
    )
    con.register("_results_df", results_df)
    con.execute(
        """
        INSERT INTO validation_results
            (validation_run_id, lot_id, season_id, rule_id, rule_version,
             result, reason, observations, missing_inputs, evaluated_at)
        SELECT validation_run_id, lot_id, season_id, rule_id, rule_version,
               result, reason, observations, missing_inputs, evaluated_at
        FROM _results_df
        """
    )
    con.unregister("_results_df")


def load_active_rules(con: duckdb.DuckDBPyConnection) -> list[Rule]:
    """The latest ACTIVE version of every rule in the store, including
    custom rules activated via the Rules page - so a subsequent Run
    Validation picks them up alongside the static C1-C9 rules."""
    rows = con.execute(
        """
        SELECT definition FROM (
            SELECT rule_id, definition, status,
                   ROW_NUMBER() OVER (PARTITION BY rule_id ORDER BY version DESC) AS rn
            FROM rule_versions
        )
        WHERE rn = 1 AND status = 'ACTIVE'
        """
    ).fetchall()
    return [Rule.model_validate_json(r[0]) for r in rows]


def load_all_rules(con: duckdb.DuckDBPyConnection) -> list[Rule]:
    """The latest version of every rule in the store, any status - for
    displaying/managing custom (agent-authored) rules on the Rules page,
    including DRAFT ones not yet picked up by Run Validation."""
    rows = con.execute(
        """
        SELECT definition FROM (
            SELECT rule_id, definition,
                   ROW_NUMBER() OVER (PARTITION BY rule_id ORDER BY version DESC) AS rn
            FROM rule_versions
        )
        WHERE rn = 1
        """
    ).fetchall()
    return [Rule.model_validate_json(r[0]) for r in rows]


def delete_rule(con: duckdb.DuckDBPyConnection, rule_id: str) -> None:
    """Removes every version of a custom rule from the store. Static
    C1-C9 rules aren't stored here as the source of truth (rules/*.yaml
    is) - deleting a rule_id that matches a static rule only clears its
    persisted copy, re-saved on the next Run Data Validation."""
    con.execute("DELETE FROM rule_versions WHERE rule_id = ?", [rule_id])


def latest_run_id(con: duckdb.DuckDBPyConnection) -> str | None:
    row = con.execute(
        "SELECT validation_run_id FROM validation_runs ORDER BY finished_at DESC LIMIT 1"
    ).fetchone()
    return row[0] if row else None
