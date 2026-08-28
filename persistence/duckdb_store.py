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

CREATE TABLE IF NOT EXISTS copilot_tool_calls (
    session_id VARCHAR,
    turn INTEGER,
    step INTEGER,
    tool_name VARCHAR,
    arguments JSON,
    success BOOLEAN,
    error VARCHAR,
    called_at TIMESTAMP
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


def list_runs(con: duckdb.DuckDBPyConnection, limit: int = 20) -> list[dict]:
    """Recent validation runs, most recent first, with readiness counts
    computed per run (a run has no stored season_id/readiness of its own -
    only validation_results does) - used by the Copilot's run-history and
    run-comparison tools."""
    rows = con.execute(
        """
        WITH recent_runs AS (
            SELECT validation_run_id, started_at, finished_at, rule_ids, row_count
            FROM validation_runs
            ORDER BY finished_at DESC
            LIMIT ?
        ),
        per_lot AS (
            SELECT validation_run_id, lot_id, season_id,
                   MAX(CASE WHEN result = 'FAIL' THEN 1 ELSE 0 END) AS has_fail,
                   MAX(CASE WHEN result = 'REVIEW' THEN 1 ELSE 0 END) AS has_review
            FROM validation_results
            WHERE validation_run_id IN (SELECT validation_run_id FROM recent_runs)
            GROUP BY 1, 2, 3
        ),
        readiness AS (
            SELECT
                validation_run_id,
                COUNT(*) AS field_season_count,
                SUM(CASE WHEN has_fail = 1 THEN 1 ELSE 0 END) AS failed_count,
                SUM(CASE WHEN has_fail = 0 AND has_review = 1 THEN 1 ELSE 0 END) AS review_count,
                SUM(CASE WHEN has_fail = 0 AND has_review = 0 THEN 1 ELSE 0 END) AS ready_count,
                string_agg(DISTINCT season_id, ',') AS season_ids
            FROM per_lot
            GROUP BY 1
        )
        SELECT
            r.validation_run_id, r.started_at, r.finished_at, r.rule_ids, r.row_count,
            COALESCE(rd.field_season_count, 0), COALESCE(rd.ready_count, 0),
            COALESCE(rd.review_count, 0), COALESCE(rd.failed_count, 0), rd.season_ids
        FROM recent_runs r
        LEFT JOIN readiness rd ON rd.validation_run_id = r.validation_run_id
        ORDER BY r.finished_at DESC
        """,
        [limit],
    ).fetchall()
    return [
        {
            "validation_run_id": r[0],
            "started_at": r[1],
            "finished_at": r[2],
            "rule_count": len(json.loads(r[3])) if r[3] else 0,
            "row_count": r[4],
            "field_season_count": r[5],
            "ready_count": r[6],
            "review_count": r[7],
            "failed_count": r[8],
            "season_ids": r[9].split(",") if r[9] else [],
        }
        for r in rows
    ]


def save_copilot_tool_call(
    con: duckdb.DuckDBPyConnection,
    session_id: str,
    turn: int,
    step: int,
    tool_name: str,
    arguments: dict,
    success: bool,
    error: str | None,
    called_at: datetime,
) -> None:
    con.execute(
        "INSERT INTO copilot_tool_calls VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        [session_id, turn, step, tool_name, json.dumps(arguments, default=str), success, error, called_at],
    )


def list_copilot_tool_calls(con: duckdb.DuckDBPyConnection, session_id: str, limit: int = 100) -> list[dict]:
    rows = con.execute(
        """
        SELECT turn, step, tool_name, arguments, success, error, called_at
        FROM copilot_tool_calls
        WHERE session_id = ?
        ORDER BY called_at DESC
        LIMIT ?
        """,
        [session_id, limit],
    ).fetchall()
    return [
        {
            "turn": r[0],
            "step": r[1],
            "tool_name": r[2],
            "arguments": json.loads(r[3]) if r[3] else {},
            "success": r[4],
            "error": r[5],
            "called_at": r[6],
        }
        for r in rows
    ]
