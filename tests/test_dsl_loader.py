import validation.operators  # noqa: F401  (registers all operators)
from validation.dsl.loader import delete_rule_file, load_all_rules, load_rule_file, save_rule_file
from validation.models import ExpressionNode, FieldRef, Rule, RuleStatus

_MINIMAL_RULE_YAML = """
rule_id: C1
name: test rule
description: test
required_inputs: [diaries.planting_date, diaries.straw_management_date]
expression:
  operator: date_after
  args:
    - field: diaries.planting_date
    - field: diaries.straw_management_date
"""


def test_delete_rule_file_removes_it(tmp_path):
    (tmp_path / "C1.yaml").write_text(_MINIMAL_RULE_YAML)
    assert len(load_all_rules(rules_dir=tmp_path, validate=False)) == 1

    delete_rule_file("C1", rules_dir=tmp_path)

    assert load_all_rules(rules_dir=tmp_path, validate=False) == []


def test_delete_rule_file_missing_file_is_a_noop(tmp_path):
    delete_rule_file("C999", rules_dir=tmp_path)  # should not raise


def test_save_rule_file_round_trips(tmp_path):
    rule = Rule(
        rule_id="C10",
        name="Promoted rule",
        version=3,
        description="A promoted custom rule.",
        required_inputs=["diaries.planting_date", "diaries.straw_management_date"],
        expression=ExpressionNode(
            operator="date_after",
            args=[FieldRef(field="diaries.planting_date"), FieldRef(field="diaries.straw_management_date")],
        ),
        status=RuleStatus.ACTIVE,
        source_text="Planting date must be after straw management date.",
    )

    path = save_rule_file(rule, rules_dir=tmp_path)

    assert path == tmp_path / "C10.yaml"
    reloaded = load_rule_file(path, validate=True)
    assert reloaded.rule_id == "C10"
    assert reloaded.status == RuleStatus.ACTIVE
    assert reloaded.expression.operator == "date_after"
    assert reloaded.required_inputs == ["diaries.planting_date", "diaries.straw_management_date"]
    # source_text/created_at/activated_at aren't part of the promoted-file
    # shape (only the base pack's own fields are), so they reset on reload.
    assert reloaded.source_text is None
