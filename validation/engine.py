"""Deterministic rule engine: expression evaluation + batch execution.

Field-season contexts are built once from the three DuckDB tables (a single
fetch per table, not a query per lot/season), then the engine walks each
rule's expression tree in Python per context. Compiling a generic Pydantic
expression DSL into fully vectorized SQL is out of scope for this PoC; this
hybrid approach (bulk fetch + per-context tree-walk) avoids N+1 queries
while keeping the DSL simple to extend. See docs/ARCHITECTURE.md.
"""

from __future__ import annotations

from datetime import date, datetime
from pathlib import Path
from typing import Any

import duckdb
import yaml

from validation.models import ExpressionNode, FieldRef, Literal, Rule
from validation.registry import registry
from validation.result_models import ResultStatus, ValidationResult

# Tables actually populated for this PoC (see adapters/csv_adapter.py), plus
# `season`: a config-derived pseudo-table (catalog/season_bounds.yaml), not
# backed by a seasons.csv since none exists in this export.
# `farmers`/`contracts`/`riceid`/`lipa` are intentionally absent - rules
# requiring them resolve to NOT_APPLICABLE rather than being faked.
AVAILABLE_TABLES = {"lots", "diaries", "photos", "fertilizer_applications", "season"}

_SEASON_BOUNDS_PATH = Path(__file__).resolve().parents[1] / "catalog" / "season_bounds.yaml"


def load_season_bounds() -> dict[str, dict[str, Any]]:
    raw = yaml.safe_load(_SEASON_BOUNDS_PATH.read_text())
    bounds = {}
    for season_id, cfg in raw.items():
        bounds[season_id] = {
            "season_id": season_id,
            "start_date": date.fromisoformat(cfg["start_date"]),
            "end_date": date.fromisoformat(cfg["end_date"]),
        }
    return bounds

_PREDICATE_OPERATORS = {"filter", "count_where", "exists", "exists_ignoring_unknown"}

Context = dict[str, Any]


def evaluate(node: ExpressionNode | FieldRef | Literal, context: Context) -> Any:
    if isinstance(node, Literal):
        return node.value
    if isinstance(node, FieldRef):
        return _resolve_field(node.field, context)
    if isinstance(node, ExpressionNode):
        return _evaluate_expression(node, context)
    raise TypeError(f"unsupported expression node type: {type(node)!r}")


def _resolve_field(field: str, context: Context) -> Any:
    table, _, column = field.partition(".")
    value = context.get(table)
    if value is None:
        return None
    if not column:
        return value
    if isinstance(value, dict):
        return value.get(column)
    return None  # collections must be reduced first via first_by/filter/etc.


def _evaluate_expression(node: ExpressionNode, context: Context) -> Any:
    if not registry.has(node.operator):
        raise KeyError(f"unknown operator: {node.operator}")
    executor = registry.get_executor(node.operator)

    if node.operator in _PREDICATE_OPERATORS:
        if len(node.args) != 2:
            raise ValueError(f"{node.operator} expects (collection, predicate) args")
        items = evaluate(node.args[0], context)
        predicate_node = node.args[1]
        return executor(items or [], predicate_node, evaluate, context, **node.params)

    resolved_args = [evaluate(arg, context) for arg in node.args]
    return executor(*resolved_args, **node.params)


def _required_tables(rule: Rule) -> set[str]:
    return {inp.split(".", 1)[0] for inp in rule.required_inputs}


def _collect_observations(rule: Rule, context: Context) -> dict[str, Any]:
    observations: dict[str, Any] = {}
    for field in rule.required_inputs:
        value = _resolve_field(field, context)
        if isinstance(value, list):
            observations[field] = f"<{len(value)} records>"
        else:
            observations[field] = value
    return observations


def _missing_inputs(rule: Rule, context: Context) -> list[str]:
    """required_inputs that are literally absent for this field-season (a
    None scalar, or an empty collection) - the data a REVIEW/FAIL-by-policy
    outcome is telling the reviewer to go find. Not a minimal causal
    witness (an operator can still return None from a non-empty collection,
    e.g. is_non_decreasing with only one dated record), just what's
    unambiguously missing."""
    missing = []
    for field in rule.required_inputs:
        value = _resolve_field(field, context)
        if value is None or (isinstance(value, list) and len(value) == 0):
            missing.append(field)
    return missing


def evaluate_rule_for_context(
    rule: Rule,
    lot_id: str,
    season_id: str,
    context: Context,
    validation_run_id: str,
    evaluated_at: datetime,
) -> ValidationResult:
    missing_tables = _required_tables(rule) - AVAILABLE_TABLES
    if missing_tables:
        return ValidationResult(
            validation_run_id=validation_run_id,
            lot_id=lot_id,
            season_id=season_id,
            rule_id=rule.rule_id,
            rule_version=rule.version,
            result=ResultStatus.NOT_APPLICABLE,
            reason=(
                f"{rule.name}: required data source(s) not available in this "
                f"dataset: {', '.join(sorted(missing_tables))}."
            ),
            observations={},
            evaluated_at=evaluated_at,
        )

    outcome = evaluate(rule.expression, context)
    observations = _collect_observations(rule, context)
    missing_inputs: list[str] = []

    if outcome is None:
        result = ResultStatus(rule.missing_data.value)
        missing_inputs = _missing_inputs(rule, context)
        reason = (
            f"{rule.name}: required data missing for this field-season; "
            f"applying missing-data policy ({rule.missing_data.value})."
        )
    elif outcome is True:
        result = ResultStatus.PASS
        reason = f"{rule.name}: condition satisfied."
    elif outcome is False:
        result = ResultStatus.FAIL
        reason = f"{rule.name}: condition not satisfied."
    else:
        raise TypeError(
            f"rule {rule.rule_id} expression must evaluate to bool or None, got {outcome!r}"
        )

    return ValidationResult(
        validation_run_id=validation_run_id,
        lot_id=lot_id,
        season_id=season_id,
        rule_id=rule.rule_id,
        rule_version=rule.version,
        result=result,
        reason=reason,
        observations=observations,
        missing_inputs=missing_inputs,
        evaluated_at=evaluated_at,
    )


def _fetch_records(
    con: duckdb.DuckDBPyConnection, table: str, season_ids: list[str] | None = None
) -> list[dict[str, Any]]:
    """Fetches a table as plain Python dicts (native date/None types), not
    via fetchdf()/pandas - pandas represents SQL NULL dates as NaT, which
    breaks None-based missing-data checks throughout the operators."""
    query = f"SELECT * FROM {table}"
    params: list[str] = []
    if season_ids:
        placeholders = ", ".join(["?"] * len(season_ids))
        query += f" WHERE CAST(season_id AS VARCHAR) IN ({placeholders})"
        params = list(season_ids)
    cursor = con.execute(query, params)
    columns = [c[0] for c in cursor.description]
    return [dict(zip(columns, row)) for row in cursor.fetchall()]


def build_field_season_contexts(
    con: duckdb.DuckDBPyConnection, season_ids: list[str] | None = None
) -> dict[tuple[str, str], Context]:
    """`season_ids`, if given, restricts the run to those season_id values
    (e.g. ["3"] for Dry Crop 2025 only) - filtered at the lots fetch, which
    drives every context key, so diaries/photos rows for excluded seasons
    are simply never attached."""
    lots_rows = _fetch_records(con, "lots", season_ids=season_ids)
    diaries_rows = _fetch_records(con, "diaries")
    photos_rows = _fetch_records(con, "photos")
    fertilizer_rows = _fetch_records(con, "fertilizer_applications")
    season_bounds = load_season_bounds()

    contexts: dict[tuple[str, str], Context] = {}
    for row in lots_rows:
        season_id = str(int(row["season_id"]))
        key = (str(row["lot_id"]), season_id)
        contexts[key] = {
            "lots": row,
            "diaries": None,
            "photos": [],
            "fertilizer_applications": [],
            "season": season_bounds.get(season_id),
        }

    for row in diaries_rows:
        key = (str(row["lot_id"]), str(int(row["season_id"])))
        if key in contexts:
            contexts[key]["diaries"] = row

    for row in photos_rows:
        key = (str(row["lot_id"]), str(int(row["season_id"])))
        if key in contexts:
            contexts[key]["photos"].append(row)

    for row in fertilizer_rows:
        key = (str(row["lot_id"]), str(int(row["season_id"])))
        if key in contexts:
            contexts[key]["fertilizer_applications"].append(row)

    for ctx in contexts.values():
        ctx["photos"].sort(key=lambda p: (p["capture_date"] is None, p["capture_date"]))
        ctx["fertilizer_applications"].sort(
            key=lambda f: (f["application_id"] is None, f["application_id"])
        )

    return contexts


def run_batch(
    con: duckdb.DuckDBPyConnection,
    rules: list[Rule],
    validation_run_id: str,
    evaluated_at: datetime | None = None,
    season_ids: list[str] | None = None,
) -> list[ValidationResult]:
    evaluated_at = evaluated_at or datetime.utcnow()
    contexts = build_field_season_contexts(con, season_ids=season_ids)
    results: list[ValidationResult] = []
    for (lot_id, season_id), context in contexts.items():
        for rule in rules:
            results.append(
                evaluate_rule_for_context(
                    rule, lot_id, season_id, context, validation_run_id, evaluated_at
                )
            )
    return results
