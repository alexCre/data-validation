"""C1-C9 tests against the real loaded dataset. Counts are locked in as a
regression baseline (captured from the current data/csv export) rather than
invented synthetic expectations, per the "no fabricated data" decision -
each count was independently derived by re-deriving the underlying SQL and
cross-checked, not just copy-pasted from a first run.
"""

import pytest

import validation.operators  # noqa: F401
from adapters import csv_adapter
from validation.dsl.loader import load_all_rules
from validation.engine import run_batch
from validation.result_models import ResultStatus


@pytest.fixture(scope="module")
def con():
    connection = csv_adapter.get_connection()
    csv_adapter.load_all(connection)
    return connection


@pytest.fixture(scope="module")
def rules():
    return load_all_rules()


@pytest.fixture(scope="module")
def results(con, rules):
    return run_batch(con, rules, validation_run_id="test-run")


def _counts(results, rule_id):
    from collections import Counter

    return Counter(r.result for r in results if r.rule_id == rule_id)


def test_all_rows_covered_by_every_rule(results, con, rules):
    # Rule count isn't hardcoded: rules/*.yaml can grow over time as custom
    # rules get promoted via the Rules page (see app/components/state.py's
    # promote_custom_rule), so this checks against whatever's actually there.
    lot_season_count = con.execute(
        "SELECT COUNT(*) FROM (SELECT DISTINCT lot_id, season_id FROM lots)"
    ).fetchone()[0]
    assert lot_season_count == 32233
    assert len(results) == lot_season_count * len(rules)


def test_c1_first_photo_category_rule(results):
    counts = _counts(results, "C1")
    assert counts[ResultStatus.PASS] == 3234
    assert counts[ResultStatus.FAIL] == 1473
    assert counts[ResultStatus.REVIEW] == 27526


def test_c2_rice_vs_non_rice(results):
    counts = _counts(results, "C2")
    assert counts[ResultStatus.PASS] == 31631
    assert counts[ResultStatus.FAIL] == 207
    assert counts[ResultStatus.REVIEW] == 395


def test_c3_non_rice_vs_rice_monitoring(results):
    counts = _counts(results, "C3")
    # No "others"-crop diary in this dataset has a non-Non-rice photo, so
    # there are no organic failures - verified directly against the data,
    # not assumed.
    assert counts[ResultStatus.PASS] == 30811
    assert counts[ResultStatus.REVIEW] == 1422
    assert counts[ResultStatus.FAIL] == 0


def test_c4_photos_outside_season(results):
    counts = _counts(results, "C4")
    assert counts[ResultStatus.PASS] == 30367
    assert counts[ResultStatus.FAIL] == 60
    assert counts[ResultStatus.REVIEW] == 1806


def test_c5_installation_before_planting(results):
    counts = _counts(results, "C5")
    assert counts[ResultStatus.PASS] == 32227
    assert counts[ResultStatus.FAIL] == 6
    assert counts[ResultStatus.REVIEW] == 0  # season bounds are always present


def test_c6_planting_vs_straw_management_has_organic_failures(results):
    counts = _counts(results, "C6")
    assert counts[ResultStatus.FAIL] > 0
    assert counts[ResultStatus.PASS] > 0
    assert counts[ResultStatus.REVIEW] > 0  # most lots have no diary at all


def test_c7_planting_outside_season(results):
    counts = _counts(results, "C7")
    assert counts[ResultStatus.PASS] == 5537
    assert counts[ResultStatus.FAIL] == 681
    assert counts[ResultStatus.REVIEW] == 26015


def test_c8_fertilizer_before_planting(results):
    # A fertilizer application record with no applied_date (a known gap in
    # this export - ~20% of records) is ignored via exists_ignoring_unknown
    # as long as another application for the same lot/season has a usable
    # date; REVIEW only remains for lot/seasons with no usable date at all.
    counts = _counts(results, "C8")
    assert counts[ResultStatus.PASS] == 31299
    assert counts[ResultStatus.FAIL] == 383
    assert counts[ResultStatus.REVIEW] == 551


def test_c9_fertilizer_sequence(results):
    counts = _counts(results, "C9")
    assert counts[ResultStatus.PASS] == 5359
    assert counts[ResultStatus.FAIL] == 183
    assert counts[ResultStatus.REVIEW] == 26691
