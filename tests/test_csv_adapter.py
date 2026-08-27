from adapters import csv_adapter


def _conn():
    con = csv_adapter.get_connection()
    csv_adapter.load_all(con)
    return con


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
