import csv

from adapters import csv_adapter
from tests.baseline_data import baseline_connection


def _conn():
    """The original Aug-2026 export, pinned - for exact golden counts."""
    return baseline_connection()


def _current_conn():
    """Whatever the app would load right now (newest export per season)."""
    con = csv_adapter.get_connection()
    csv_adapter.load_all(con)
    return con


def _live_row_count(path, require_field_id=False):
    """Independent count of is_deleted = false rows straight from the CSV."""
    with open(path, newline="", encoding="utf-8-sig") as fh:
        rows = csv.DictReader(fh)
        return sum(
            1
            for r in rows
            if r["is_deleted"].lower() == "false" and (not require_field_id or r["field_id"])
        )


def test_lots_row_count_matches_is_deleted_false():
    con = _conn()
    count = con.execute("SELECT COUNT(*) FROM lots").fetchone()[0]
    assert count == 32233


def test_lots_no_pii_columns():
    con = _conn()
    columns = {c[0] for c in con.execute("DESCRIBE lots").fetchall()}
    assert "owner_name" not in columns
    assert "rice_specialist" not in columns


def test_lots_season_ids_present():
    con = _conn()
    seasons = {r[0] for r in con.execute("SELECT DISTINCT season_id FROM lots").fetchall()}
    assert seasons == {3, 4}


def test_diaries_deduplicated_from_fertilizer_fanout():
    con = _conn()
    count = con.execute("SELECT COUNT(*) FROM diaries").fetchone()[0]
    distinct_ids = con.execute("SELECT COUNT(DISTINCT diary_id) FROM diaries").fetchone()[0]
    assert count == distinct_ids
    assert count == 23383


def test_photos_excludes_unmatched_and_deleted():
    con = _conn()
    count = con.execute("SELECT COUNT(*) FROM photos").fetchone()[0]
    assert count == 39605
    null_lots = con.execute("SELECT COUNT(*) FROM photos WHERE lot_id IS NULL").fetchone()[0]
    assert null_lots == 0


def test_fertilizer_applications_loaded_from_diary_fanout():
    con = _conn()
    count = con.execute("SELECT COUNT(*) FROM fertilizer_applications").fetchone()[0]
    assert count == 111377
    distinct_ids = con.execute(
        "SELECT COUNT(DISTINCT application_id) FROM fertilizer_applications"
    ).fetchone()[0]
    assert count == distinct_ids


def test_declared_area_converted_to_hectares():
    con = _conn()
    row = con.execute(
        "SELECT declared_area_ha FROM lots WHERE declared_area_ha IS NOT NULL LIMIT 1"
    ).fetchone()
    assert row[0] < 100  # sanity: hectares, not raw sqm


# ---- invariants on whatever the CURRENT data is (not tied to exact counts) --


def test_current_data_loads_every_pangasinan_season():
    con = _current_conn()
    seasons = {r[0] for r in con.execute("SELECT DISTINCT season_id FROM lots").fetchall()}
    assert seasons == {3, 4, 5}  # Dry Crop 2025, Wet Crop 2025, Dry Crop 2026


def test_current_data_rows_match_the_selected_csvs():
    """Per season, the loaded row counts equal an independent count of the
    newest CSV selected for that season - so a freshly dropped export is
    reflected exactly, without editing any golden numbers."""
    con = _current_conn()
    for season_id, path in csv_adapter.fields_sources().items():
        loaded = con.execute("SELECT COUNT(*) FROM lots WHERE season_id = ?", [season_id]).fetchone()[0]
        assert loaded == _live_row_count(path), (season_id, path.name)
    for season_id, path in csv_adapter.photos_sources().items():
        loaded = con.execute("SELECT COUNT(*) FROM photos WHERE season_id = ?", [season_id]).fetchone()[0]
        assert loaded == _live_row_count(path, require_field_id=True), (season_id, path.name)


def test_current_data_dry_2025_and_dry_2026_are_separate_seasons():
    con = _current_conn()
    overlap = con.execute(
        """
        SELECT COUNT(*) FROM (
            SELECT lot_id FROM lots WHERE season_id = 3
            INTERSECT
            SELECT lot_id FROM lots WHERE season_id = 5
        )
        """
    ).fetchone()[0]
    # Distinct field populations, not one file loaded under two seasons.
    n3 = con.execute("SELECT COUNT(*) FROM lots WHERE season_id = 3").fetchone()[0]
    n5 = con.execute("SELECT COUNT(*) FROM lots WHERE season_id = 5").fetchone()[0]
    assert n3 > 0 and n5 > 0
    assert overlap < min(n3, n5)


def test_current_data_diaries_and_photos_are_clean():
    con = _current_conn()
    d_count, d_ids = con.execute("SELECT COUNT(*), COUNT(DISTINCT diary_id || '-' || season_id) FROM diaries").fetchone()
    assert d_count == d_ids
    assert con.execute("SELECT COUNT(*) FROM photos WHERE lot_id IS NULL").fetchone()[0] == 0
