"""End-to-end: load real CSVs -> run C1-C9 -> persist to DuckDB -> query
dashboard-style aggregates -> export filtered results to CSV.
"""

import io
from datetime import datetime

import pandas as pd

import validation.operators  # noqa: F401
from adapters import csv_adapter
from persistence import duckdb_store
from validation.dsl.loader import load_all_rules
from validation.engine import run_batch
from validation.result_models import ResultStatus, compute_readiness


def test_end_to_end(tmp_path):
    data_con = csv_adapter.get_connection()
    csv_adapter.load_all(data_con)
    rules = load_all_rules()

    started_at = datetime.utcnow()
    results = run_batch(data_con, rules, validation_run_id="itest-run")
    finished_at = datetime.utcnow()
    assert results

    store_con = duckdb_store.get_connection(tmp_path / "itest.duckdb")
    for rule in rules:
        duckdb_store.save_rule_version(store_con, rule)
    duckdb_store.save_results(
        store_con,
        "itest-run",
        [r.rule_id for r in rules],
        results,
        started_at,
        finished_at,
    )

    assert duckdb_store.latest_run_id(store_con) == "itest-run"

    stored_count = store_con.execute(
        "SELECT COUNT(*) FROM validation_results WHERE validation_run_id = 'itest-run'"
    ).fetchone()[0]
    assert stored_count == len(results)

    # dashboard-style aggregate: readiness per field-season
    by_field_season: dict[tuple, list] = {}
    for r in results:
        by_field_season.setdefault((r.lot_id, r.season_id), []).append(r)
    readiness_counts = {"READY": 0, "NEEDS_REVIEW": 0, "FAILED": 0}
    for group in by_field_season.values():
        readiness_counts[compute_readiness(group).value] += 1
    assert sum(readiness_counts.values()) == len(by_field_season)
    assert readiness_counts["FAILED"] > 0

    # filtered CSV export, local + deterministic, no LLM involved
    fail_c5 = [r for r in results if r.rule_id == "C5" and r.result == ResultStatus.FAIL]
    assert fail_c5
    df = pd.DataFrame([r.model_dump() for r in fail_c5])
    buf = io.StringIO()
    df.to_csv(buf, index=False)
    csv_text = buf.getvalue()
    assert "C5" in csv_text
    assert csv_text.count("\n") - 1 == len(fail_c5)  # header + one row per result
