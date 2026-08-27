from persistence import duckdb_store
from validation.models import ExpressionNode, FieldRef, Rule, RuleStatus


def _rule(rule_id, version, status):
    return Rule(
        rule_id=rule_id,
        name=f"{rule_id} v{version}",
        version=version,
        description="test",
        required_inputs=["diaries.planting_date", "diaries.straw_management_date"],
        expression=ExpressionNode(
            operator="date_after",
            args=[FieldRef(field="diaries.planting_date"), FieldRef(field="diaries.straw_management_date")],
        ),
        status=status,
    )


def test_load_active_rules_returns_only_active(tmp_path):
    con = duckdb_store.get_connection(tmp_path / "t.duckdb")
    duckdb_store.save_rule_version(con, _rule("CUSTOM_A", 1, RuleStatus.DRAFT))
    duckdb_store.save_rule_version(con, _rule("CUSTOM_B", 1, RuleStatus.ACTIVE))

    active = {r.rule_id: r for r in duckdb_store.load_active_rules(con)}
    assert set(active) == {"CUSTOM_B"}


def test_load_active_rules_picks_latest_version(tmp_path):
    con = duckdb_store.get_connection(tmp_path / "t2.duckdb")
    duckdb_store.save_rule_version(con, _rule("CUSTOM_C", 1, RuleStatus.ACTIVE))
    duckdb_store.save_rule_version(con, _rule("CUSTOM_C", 2, RuleStatus.ACTIVE))

    active = {r.rule_id: r for r in duckdb_store.load_active_rules(con)}
    assert active["CUSTOM_C"].version == 2


def test_load_all_rules_includes_draft_and_active(tmp_path):
    con = duckdb_store.get_connection(tmp_path / "t_all.duckdb")
    duckdb_store.save_rule_version(con, _rule("CUSTOM_E", 1, RuleStatus.DRAFT))
    duckdb_store.save_rule_version(con, _rule("CUSTOM_F", 1, RuleStatus.ACTIVE))

    all_rules = {r.rule_id: r for r in duckdb_store.load_all_rules(con)}
    assert set(all_rules) == {"CUSTOM_E", "CUSTOM_F"}


def test_load_all_rules_picks_latest_version(tmp_path):
    con = duckdb_store.get_connection(tmp_path / "t_all2.duckdb")
    duckdb_store.save_rule_version(con, _rule("CUSTOM_G", 1, RuleStatus.DRAFT))
    duckdb_store.save_rule_version(con, _rule("CUSTOM_G", 2, RuleStatus.DRAFT))

    all_rules = {r.rule_id: r for r in duckdb_store.load_all_rules(con)}
    assert all_rules["CUSTOM_G"].version == 2


def test_delete_rule_removes_every_version(tmp_path):
    con = duckdb_store.get_connection(tmp_path / "t_del.duckdb")
    duckdb_store.save_rule_version(con, _rule("CUSTOM_H", 1, RuleStatus.DRAFT))
    duckdb_store.save_rule_version(con, _rule("CUSTOM_H", 2, RuleStatus.ACTIVE))
    duckdb_store.save_rule_version(con, _rule("CUSTOM_I", 1, RuleStatus.ACTIVE))

    duckdb_store.delete_rule(con, "CUSTOM_H")

    remaining = {r.rule_id for r in duckdb_store.load_all_rules(con)}
    assert remaining == {"CUSTOM_I"}
    assert con.execute(
        "SELECT COUNT(*) FROM rule_versions WHERE rule_id = 'CUSTOM_H'"
    ).fetchone()[0] == 0


def test_activated_custom_rule_participates_in_a_later_batch_run(tmp_path):
    """Regression test for DoD #9: an activated custom rule must run in a
    subsequent validation, not just the static C1-C9 rules."""
    import validation.operators  # noqa: F401
    from adapters import csv_adapter
    from validation.dsl.loader import load_all_rules
    from validation.engine import run_batch

    con = duckdb_store.get_connection(tmp_path / "t3.duckdb")
    static_rules = load_all_rules()
    for r in static_rules:
        duckdb_store.save_rule_version(con, r)
    duckdb_store.save_rule_version(con, _rule("CUSTOM_D", 1, RuleStatus.ACTIVE))

    combined = {r.rule_id: r for r in duckdb_store.load_active_rules(con)}
    combined.update({r.rule_id: r for r in static_rules})

    data_con = csv_adapter.get_connection()
    csv_adapter.load_all(data_con)
    results = run_batch(data_con, list(combined.values()), "run-x")

    assert any(r.rule_id == "CUSTOM_D" for r in results)
    assert any(r.rule_id == "C1" for r in results)
