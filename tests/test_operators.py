from datetime import date, datetime

import pytest

import validation.operators  # noqa: F401  (registers all operators)
from validation.registry import registry


def run(name, *args, **params):
    return registry.get_executor(name)(*args, **params)


# --- temporal ---


def test_date_after_true():
    assert run("date_after", date(2024, 11, 24), date(2024, 10, 30)) is True


def test_date_after_false():
    assert run("date_after", date(2024, 10, 1), date(2024, 10, 30)) is False


def test_date_after_missing():
    assert run("date_after", None, date(2024, 10, 30)) is None


def test_date_before_datetime_input():
    assert run("date_before", datetime(2024, 10, 30, 9, 0), datetime(2024, 11, 24, 9, 0)) is True


def test_date_between_inclusive_bounds():
    assert run("date_between", date(2024, 10, 1), date(2024, 10, 1), date(2024, 10, 31)) is True


def test_date_between_outside_range():
    assert run("date_between", date(2024, 9, 30), date(2024, 10, 1), date(2024, 10, 31)) is False


def test_days_between():
    assert run("days_between", date(2024, 10, 1), date(2024, 10, 11)) == 10


def test_add_days_forward():
    assert run("add_days", date(2024, 11, 24), 120) == date(2025, 3, 24)


def test_add_days_missing():
    assert run("add_days", None, 120) is None


def test_add_months_negative():
    assert run("add_months", date(2024, 10, 21), -1) == date(2024, 9, 21)


def test_add_months_positive():
    assert run("add_months", date(2025, 4, 11), 3) == date(2025, 7, 11)


# --- categorical ---


def test_equals_true():
    assert run("equals", "rice", "rice") is True


def test_equals_missing():
    assert run("equals", None, "rice") is None


def test_is_present_true_when_value_given():
    assert run("is_present", date(2024, 11, 24)) is True


def test_is_present_false_when_none():
    assert run("is_present", None) is False


def test_in_set_true():
    assert run("in_set", "Installation", values=["Installation", "Non-rice"]) is True


def test_in_set_false():
    assert run("in_set", "Drainage", values=["Installation", "Non-rice"]) is False


def test_mapped_equals_true():
    mapping = {"rice": ["Installation", "Drainage"]}
    assert run("mapped_equals", "rice", "Installation", mapping=mapping) is True


def test_mapped_equals_false():
    mapping = {"rice": ["Installation", "Drainage"]}
    assert run("mapped_equals", "rice", "Non-rice", mapping=mapping) is False


def test_mapped_equals_unknown_source_key():
    mapping = {"rice": ["Installation"]}
    assert run("mapped_equals", "others", "Installation", mapping=mapping) is False


# --- logical ---


def test_and_all_true():
    assert run("and", True, True) is True


def test_and_short_circuits_false_over_none():
    assert run("and", False, None) is False


def test_and_unknown_propagates():
    assert run("and", True, None) is None


def test_or_short_circuits_true_over_none():
    assert run("or", True, None) is True


def test_not_none():
    assert run("not", None) is None


def test_if_then_condition_false_is_vacuously_true():
    assert run("if_then", False, False) is True


def test_if_then_condition_true_passes_through_then():
    assert run("if_then", True, False) is False


# --- numeric ---


def test_percentage_difference():
    assert run("percentage_difference", 11.0, 10.0) == pytest.approx(10.0)


def test_percentage_difference_zero_reference():
    assert run("percentage_difference", 5.0, 0.0) is None


def test_within_range_edge_case():
    assert run("within_range", 5000.0, 4700.0, 5391.0) is True


# --- sequence ---


def test_first_by_picks_earliest():
    items = [
        {"capture_date": date(2025, 1, 10), "category": "Drainage"},
        {"capture_date": date(2025, 1, 1), "category": "Installation"},
    ]
    assert run("first_by", items, key_field="capture_date")["category"] == "Installation"


def test_first_by_empty_list():
    assert run("first_by", [], key_field="capture_date") is None


def test_count():
    assert run("count", [1, 2, 3]) == 3


def _predicate_run(name, items, predicate_fn):
    executor = registry.get_executor(name)
    return executor(items, None, lambda node, ctx: predicate_fn(ctx["item"]), {})


def test_exists_ignoring_unknown_true_when_one_known_true():
    items = [{"v": None}, {"v": True}, {"v": False}]
    assert _predicate_run("exists_ignoring_unknown", items, lambda i: i["v"]) is True


def test_exists_ignoring_unknown_ignores_unknown_when_rest_are_known_false():
    items = [{"v": None}, {"v": False}, {"v": False}]
    assert _predicate_run("exists_ignoring_unknown", items, lambda i: i["v"]) is False


def test_exists_ignoring_unknown_none_when_all_unknown():
    items = [{"v": None}, {"v": None}]
    assert _predicate_run("exists_ignoring_unknown", items, lambda i: i["v"]) is None


def test_exists_ignoring_unknown_false_on_empty_list():
    assert _predicate_run("exists_ignoring_unknown", [], lambda i: True) is False


def test_get_field_none_record():
    from validation.operators.relational import get_field

    assert get_field(None, field_name="category") is None


# --- spatial ---


def test_geometry_exists_true():
    assert run("geometry_exists", "POLYGON ((0 0, 0 1, 1 1, 1 0, 0 0))") is True


def test_geometry_exists_false_on_none():
    assert run("geometry_exists", None) is False


def test_geometry_area_ha_small_square():
    # ~0.001 degree square near the equator is roughly 1.24 ha geodesically.
    wkt = "POLYGON ((0 0, 0 0.001, 0.001 0.001, 0.001 0, 0 0))"
    area = run("geometry_area_ha", wkt)
    assert 1.0 < area < 1.5


# --- relational ---


def test_related_record_exists_false_on_none():
    assert run("related_record_exists", None) is False


def test_status_equals():
    assert run("status_equals", "SIGNED", "SIGNED") is True


def test_dataset_membership():
    assert run("dataset_membership", "abc", dataset=["abc", "def"]) is True
    assert run("dataset_membership", "xyz", dataset=["abc", "def"]) is False
