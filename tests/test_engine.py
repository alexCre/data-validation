from datetime import date, datetime

import validation.operators  # noqa: F401  (registers all operators)
from validation.engine import evaluate_rule_for_context
from validation.models import ExpressionNode, FieldRef, Rule
from validation.result_models import ResultStatus


def _rule(expression: ExpressionNode, required_inputs: list[str]) -> Rule:
    return Rule(
        rule_id="TEST",
        name="test rule",
        description="test",
        required_inputs=required_inputs,
        expression=expression,
    )


def _run(rule: Rule, context: dict) -> ResultStatus:
    return evaluate_rule_for_context(rule, "lot-1", "3", context, "run-1", datetime.utcnow())


def test_missing_inputs_reports_none_scalar_field():
    rule = _rule(
        ExpressionNode(
            operator="date_after",
            args=[FieldRef(field="diaries.planting_date"), FieldRef(field="diaries.straw_management_date")],
        ),
        ["diaries.planting_date", "diaries.straw_management_date"],
    )
    result = _run(rule, {"diaries": None})
    assert result.result == ResultStatus.REVIEW
    assert result.missing_inputs == ["diaries.planting_date", "diaries.straw_management_date"]


def test_missing_inputs_reports_empty_collection():
    rule = _rule(
        ExpressionNode(
            operator="get_field",
            args=[
                ExpressionNode(operator="first_by", args=[FieldRef(field="photos")], params={"key_field": "capture_date"}),
            ],
            params={"field_name": "category"},
        ),
        ["photos"],
    )
    result = _run(rule, {"photos": []})
    assert result.result == ResultStatus.REVIEW
    assert result.missing_inputs == ["photos"]


def test_missing_inputs_empty_when_rule_resolves():
    rule = _rule(
        ExpressionNode(
            operator="date_after",
            args=[FieldRef(field="diaries.planting_date"), FieldRef(field="diaries.straw_management_date")],
        ),
        ["diaries.planting_date", "diaries.straw_management_date"],
    )
    result = _run(
        rule,
        {"diaries": {"planting_date": date(2024, 11, 24), "straw_management_date": date(2024, 10, 30)}},
    )
    assert result.result == ResultStatus.PASS
    assert result.missing_inputs == []


def _fertilizer_before_planting_rule() -> Rule:
    return _rule(
        ExpressionNode(
            operator="not",
            args=[
                ExpressionNode(
                    operator="exists_ignoring_unknown",
                    args=[
                        FieldRef(field="fertilizer_applications"),
                        ExpressionNode(
                            operator="date_before",
                            args=[FieldRef(field="item.applied_date"), FieldRef(field="diaries.planting_date")],
                        ),
                    ],
                )
            ],
        ),
        ["diaries.planting_date", "fertilizer_applications"],
    )


def test_exists_ignoring_unknown_ignores_one_bad_record_among_good_ones():
    """Regression test for the 1485-A case: one fertilizer application with
    no applied_date shouldn't drag an otherwise-clean lot into REVIEW."""
    rule = _fertilizer_before_planting_rule()
    context = {
        "diaries": {"planting_date": date(2024, 11, 30)},
        "fertilizer_applications": [
            {"application_id": 1, "applied_date": date(2024, 12, 10)},
            {"application_id": 2, "applied_date": date(2024, 12, 20)},
            {"application_id": 3, "applied_date": None},
        ],
    }
    result = _run(rule, context)
    assert result.result == ResultStatus.PASS


def test_exists_ignoring_unknown_still_reviews_when_all_records_are_unknown():
    rule = _fertilizer_before_planting_rule()
    context = {
        "diaries": {"planting_date": date(2024, 11, 30)},
        "fertilizer_applications": [
            {"application_id": 1, "applied_date": None},
            {"application_id": 2, "applied_date": None},
        ],
    }
    result = _run(rule, context)
    assert result.result == ResultStatus.REVIEW


def test_exists_ignoring_unknown_still_catches_a_real_violation():
    rule = _fertilizer_before_planting_rule()
    context = {
        "diaries": {"planting_date": date(2024, 11, 30)},
        "fertilizer_applications": [
            {"application_id": 1, "applied_date": date(2024, 11, 1)},  # before planting - violation
            {"application_id": 2, "applied_date": None},
        ],
    }
    result = _run(rule, context)
    assert result.result == ResultStatus.FAIL
