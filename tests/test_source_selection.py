"""Which CSV the adapter picks for each season: always the newest export,
and a season is never confused with another year's export of the same
dry/wet season."""

import os

import pytest

from adapters import csv_adapter


@pytest.fixture
def region_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(csv_adapter, "region_csv_dir", lambda region: tmp_path)
    return tmp_path


def _touch(directory, *names, mtime=None):
    for name in names:
        path = directory / name
        path.write_text("x\n")
        if mtime is not None:
            os.utime(path, (mtime, mtime))


def _picked(table, season_id, region="pangasinan"):
    sources = csv_adapter._sources_for(region, table)
    return sources[season_id].name if season_id in sources else None


def test_newest_export_timestamp_wins_for_the_same_season(region_dir):
    _touch(
        region_dir,
        "fields-wet-crop-2025-202608241809.csv",
        "fields-wet-crop-2025-202610251922.csv",
        "fields-wet-crop-2025-202609010000.csv",
    )
    assert _picked("fields", 4) == "fields-wet-crop-2025-202610251922.csv"


def test_newest_wins_even_if_an_older_file_has_a_newer_mtime(region_dir):
    _touch(region_dir, "fields-wet-crop-2025-202610251922.csv", mtime=1_000)
    _touch(region_dir, "fields-wet-crop-2025-202608241809.csv", mtime=9_999_999_999)
    assert _picked("fields", 4) == "fields-wet-crop-2025-202610251922.csv"


def test_naming_variants_compete_on_export_time_not_pattern_order(region_dir):
    # old export used "field-photo-", the newer one "field-photos-"
    _touch(
        region_dir,
        "field-photo-wet-crop-2025-202608261615.csv",
        "field-photos-wet-crop-2025-202610251922.csv",
    )
    assert _picked("photos", 4) == "field-photos-wet-crop-2025-202610251922.csv"
    # ...and the other way round: a later export under the old name still wins
    _touch(region_dir, "field-photo-wet-crop-2025-202611010000.csv")
    assert _picked("photos", 4) == "field-photo-wet-crop-2025-202611010000.csv"


def test_dry_2025_and_dry_2026_are_different_seasons(region_dir):
    _touch(
        region_dir,
        "fields-dry-crop-2025-202608241808.csv",
        "fields-dry-crop-2026-202610251924.csv",
    )
    assert _picked("fields", 3) == "fields-dry-crop-2025-202608241808.csv"
    assert _picked("fields", 5) == "fields-dry-crop-2026-202610251924.csv"


def test_a_newer_export_of_another_year_never_replaces_a_season(region_dir):
    _touch(region_dir, "fields-dry-crop-2025-202608241808.csv")
    _touch(region_dir, "fields-dry-crop-2026-202610251924.csv")
    # a re-export of Dry Crop 2025 later on only affects season 3
    _touch(region_dir, "fields-dry-crop-2025-202612010000.csv")
    assert _picked("fields", 3) == "fields-dry-crop-2025-202612010000.csv"
    assert _picked("fields", 5) == "fields-dry-crop-2026-202610251924.csv"


def test_seasons_without_a_file_are_omitted(region_dir):
    _touch(region_dir, "fields-dry-crop-2026-202610251924.csv")
    assert set(csv_adapter._sources_for("pangasinan", "fields")) == {5}


def test_cagayan_selection_still_works(region_dir):
    _touch(
        region_dir,
        "field-ds2026-cagayan-202609081215.csv",
        "field-ds2026-cagayan-202610010000.csv",
    )
    assert _picked("fields", 5, region="cagayan") == "field-ds2026-cagayan-202610010000.csv"


def test_fingerprint_changes_when_a_newer_export_arrives(region_dir):
    _touch(region_dir, "fields-wet-crop-2025-202608241809.csv")
    before = csv_adapter.source_fingerprint("pangasinan")
    _touch(region_dir, "fields-wet-crop-2025-202610251922.csv")
    after = csv_adapter.source_fingerprint("pangasinan")
    assert before != after
    assert csv_adapter.source_fingerprint("pangasinan") == after  # stable when nothing changes
