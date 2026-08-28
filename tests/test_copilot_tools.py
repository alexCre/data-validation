"""Tool-layer tests for the Validation Copilot: each tool exercised
directly through the registry (bypassing the LLM entirely), against a real
validation run over the real dataset.
"""

import os

import pytest
from pydantic import ValidationError

import validation.operators  # noqa: F401
from app.components.state import run_validation
from copilot.service import build_default_registry
from copilot.tool_registry import ToolNotFoundError
from copilot.tools._common import NoValidationRunError


@pytest.fixture(scope="module")
def run_id():
    return run_validation(season_ids=["3"])


@pytest.fixture(scope="module")
def registry():
    return build_default_registry()


# --- registry guardrails ---


def test_unknown_tool_is_rejected(registry):
    with pytest.raises(ToolNotFoundError):
        registry.call("delete_everything", {})


def test_invalid_arguments_are_rejected(registry, run_id):
    with pytest.raises(ValidationError):
        registry.call("get_field_findings", {"season_id": "3", "validation_run_id": run_id})  # missing lot_id


def test_no_validation_run_raises_clear_error(registry, monkeypatch):
    # No validation_run_id given and no run has ever completed in this store.
    monkeypatch.setattr("copilot.tools._common.latest_run_id", lambda: None)
    with pytest.raises(NoValidationRunError):
        registry.call("get_validation_summary", {})


def test_unknown_explicit_run_id_yields_empty_result_not_a_crash(registry):
    # An explicitly-given (but nonexistent) run_id is a data question, not a
    # guardrail violation - it should resolve to "nothing found", not raise.
    out = registry.call("get_validation_summary", {"validation_run_id": "run-does-not-exist"})
    assert out.total_field_seasons == 0


# --- get_validation_summary ---


def test_validation_summary_totals(registry, run_id):
    out = registry.call("get_validation_summary", {"validation_run_id": run_id})
    assert out.total_field_seasons > 0
    assert out.ready_count + out.review_required_count + out.validation_failed_count == out.total_field_seasons
    assert len(out.top_issues) > 0


def test_validation_summary_season_filter_narrows_result(registry, run_id):
    out_all = registry.call("get_validation_summary", {"validation_run_id": run_id})
    out_season = registry.call("get_validation_summary", {"validation_run_id": run_id, "season_id": "3"})
    assert out_season.total_field_seasons == out_all.total_field_seasons  # only season 3 was run
    out_missing_season = registry.call(
        "get_validation_summary", {"validation_run_id": run_id, "season_id": "999"}
    )
    assert out_missing_season.total_field_seasons == 0


# --- get_top_validation_issues ---


def test_top_validation_issues_respects_limit(registry, run_id):
    out = registry.call("get_top_validation_issues", {"validation_run_id": run_id, "limit": 3})
    assert len(out.issues) <= 3


def test_top_validation_issues_result_filter(registry, run_id):
    out = registry.call("get_top_validation_issues", {"validation_run_id": run_id, "result": "FAIL", "limit": 10})
    assert all(i.result == "FAIL" for i in out.issues)


def test_top_validation_issues_rejects_bad_limit(registry, run_id):
    with pytest.raises(ValidationError):
        registry.call("get_top_validation_issues", {"validation_run_id": run_id, "limit": 0})


# --- get_validation_results ---


def test_validation_results_pagination(registry, run_id):
    page1 = registry.call("get_validation_results", {"validation_run_id": run_id, "limit": 5, "offset": 0})
    page2 = registry.call("get_validation_results", {"validation_run_id": run_id, "limit": 5, "offset": 5})
    assert page1.returned == 5
    assert page1.truncated is True
    assert [r.lot_id for r in page1.rows] != [r.lot_id for r in page2.rows]


def test_validation_results_never_exceeds_max_limit(registry, run_id):
    with pytest.raises(ValidationError):
        registry.call("get_validation_results", {"validation_run_id": run_id, "limit": 10_000})


def test_validation_results_filters_by_rule_and_result(registry, run_id):
    out = registry.call(
        "get_validation_results", {"validation_run_id": run_id, "rule_id": "C6", "result": "FAIL", "limit": 50}
    )
    assert out.total_matching > 0
    assert all(r.rule_id == "C6" and r.result == "FAIL" for r in out.rows)


def test_validation_results_empty_for_impossible_filter(registry, run_id):
    out = registry.call(
        "get_validation_results", {"validation_run_id": run_id, "lot_id": "no-such-lot", "limit": 10}
    )
    assert out.total_matching == 0
    assert out.rows == []


# --- get_field_validation_summary / get_field_findings ---


def test_field_validation_summary_found(registry, run_id):
    any_field = registry.call("get_validation_results", {"validation_run_id": run_id, "limit": 1}).rows[0]
    out = registry.call(
        "get_field_validation_summary",
        {"lot_id": any_field.lot_id, "season_id": any_field.season_id, "validation_run_id": run_id},
    )
    assert out.found is True
    assert out.readiness in {"READY", "NEEDS_REVIEW", "FAILED"}


def test_field_validation_summary_not_found(registry, run_id):
    out = registry.call(
        "get_field_validation_summary", {"lot_id": "no-such-lot", "season_id": "3", "validation_run_id": run_id}
    )
    assert out.found is False


def test_field_findings_returns_structured_reasons(registry, run_id):
    any_field = registry.call("get_validation_results", {"validation_run_id": run_id, "limit": 1}).rows[0]
    out = registry.call(
        "get_field_findings",
        {"lot_id": any_field.lot_id, "season_id": any_field.season_id, "validation_run_id": run_id},
    )
    assert out.found is True
    assert len(out.findings) > 0
    assert all(f.reason for f in out.findings)


def test_field_findings_result_filter(registry, run_id):
    out = registry.call(
        "get_field_findings",
        {"lot_id": "123437", "season_id": "3", "validation_run_id": run_id, "result": "FAIL"},
    )
    assert all(f.result == "FAIL" for f in out.findings)


# --- get_rule_details ---


def test_rule_details_known_rule(registry):
    out = registry.call("get_rule_details", {"rule_id": "C6"})
    assert out.found is True
    assert out.name
    assert out.missing_data_policy in {"PASS", "FAIL", "REVIEW", "NOT_APPLICABLE"}


def test_rule_details_unknown_rule(registry):
    out = registry.call("get_rule_details", {"rule_id": "C999"})
    assert out.found is False


# --- compare_validation_runs ---


def test_compare_identical_run_has_no_changes(registry, run_id):
    out = registry.call("compare_validation_runs", {"run_a": run_id, "run_b": run_id})
    assert out.found is True
    assert out.ready_change == 0
    assert out.review_required_change == 0
    assert out.failed_change == 0
    assert out.newly_failing_count == 0
    assert out.resolved_count == 0


def test_compare_unknown_run_reports_not_found(registry, run_id):
    out = registry.call("compare_validation_runs", {"run_a": run_id, "run_b": "run-does-not-exist"})
    assert out.found is False


# --- get_validation_run_history ---


def test_run_history_returns_recent_runs(registry, run_id):
    out = registry.call("get_validation_run_history", {"limit": 5})
    assert any(r.validation_run_id == run_id for r in out.runs)


# --- export_validation_csv ---


def test_export_field_summary_creates_downloadable_file(registry, run_id):
    out = registry.call("export_validation_csv", {"mode": "FIELD_SUMMARY", "validation_run_id": run_id})
    assert out.row_count > 0
    assert os.path.exists(out.file_path)
    with open(out.file_path) as f:
        header = f.readline()
    assert "readiness" in header


def test_export_detailed_respects_filters(registry, run_id):
    out = registry.call(
        "export_validation_csv",
        {"mode": "DETAILED", "validation_run_id": run_id, "rule_id": "C6", "result": "FAIL"},
    )
    assert out.row_count > 0
    with open(out.file_path) as f:
        lines = f.readlines()
    assert all("C6" in line for line in lines[1:])
    assert os.path.exists(out.file_path)


def test_export_rejects_invalid_mode(registry, run_id):
    with pytest.raises(ValueError):
        registry.call("export_validation_csv", {"mode": "BOGUS", "validation_run_id": run_id})


# --- request_new_rule (mock provider path is exercised in test_copilot_agent.py;
#     here we only check the registry wiring returns a well-formed output) ---


def test_request_new_rule_returns_a_status(registry, monkeypatch):
    # Force the offline mock path so this test is deterministic and never
    # makes a real API call, matching every other agent test in this suite.
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    out = registry.call("request_new_rule", {"rule_text": "Planting date must be after straw management date."})
    assert out.status in {"COMPILED", "NEEDS_CLARIFICATION", "UNSUPPORTED_CAPABILITY"}
    assert out.request_id
