import pytest
from pydantic import ValidationError

import validation.operators  # noqa: F401
from catalog.loader import known_fields
from validation.dsl.validate import validate_rule
from validation.models import ExpressionNode, FieldRef, Literal, Rule


def make_rule(expression: ExpressionNode) -> Rule:
    return Rule(
        rule_id="TEST",
        name="test rule",
        description="test",
        required_inputs=[],
        expression=expression,
    )


def test_valid_rule_has_no_errors():
    rule = make_rule(
        ExpressionNode(
            operator="date_after",
            args=[FieldRef(field="diaries.planting_date"), FieldRef(field="diaries.straw_management_date")],
        )
    )
    assert validate_rule(rule, known_fields()) == []


def test_rejects_hallucinated_operator():
    rule = make_rule(
        ExpressionNode(operator="classify_field_stage", args=[FieldRef(field="photos")])
    )
    errors = validate_rule(rule, known_fields())
    assert any("unknown operator" in e for e in errors)


def test_rejects_unknown_field_reference():
    rule = make_rule(
        ExpressionNode(
            operator="date_after",
            args=[FieldRef(field="diaries.made_up_field"), FieldRef(field="diaries.planting_date")],
        )
    )
    errors = validate_rule(rule, known_fields())
    assert any("unknown field reference" in e for e in errors)


def test_rejects_wrong_argument_count():
    rule = make_rule(
        ExpressionNode(operator="date_after", args=[FieldRef(field="diaries.planting_date")])
    )
    errors = validate_rule(rule, known_fields())
    assert any("expects 2 args" in e for e in errors)


def test_item_scoped_fields_always_allowed():
    rule = make_rule(
        ExpressionNode(operator="equals", args=[FieldRef(field="item.category"), Literal(value="Installation")])
    )
    assert validate_rule(rule, known_fields()) == []


def test_malformed_expression_missing_operator_key_rejected_by_pydantic():
    with pytest.raises(ValidationError):
        Rule(
            rule_id="TEST2",
            name="bad",
            description="test",
            required_inputs=[],
            expression={"args": []},  # missing required "operator" key
        )
