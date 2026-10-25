"""The original (Aug 2026) Pangasinan export, pinned by filename.

The C1-C9 / adapter regression tests lock in exact counts as a baseline
captured from THIS export. The app always loads the newest export per season
(adapters.csv_adapter), so those counts would shift every time fresh data is
dropped into data/pangasinan/csv. Pinning the baseline to explicit files keeps
the golden counts meaningful no matter how the "latest" selection changes -
the superseded CSVs just need to stay in the folder (tests skip, not fail, if
they've been removed). Counts that should track whatever data is current live
in test_csv_adapter.py's invariant tests instead.
"""

import pytest

from adapters import csv_adapter

_DIR = csv_adapter.region_csv_dir("pangasinan")

BASELINE_SOURCES = {
    "fields": {3: "fields-dry-crop-2025-202608241808.csv", 4: "fields-wet-crop-2025-202608241809.csv"},
    "diaries": {3: "field-diaries-dry-crop-2025-202608241811.csv", 4: "field-diaries-wet-crop-2025-202608261648.csv"},
    "photos": {3: "field-photos-dry-crop-2025-202608241816.csv", 4: "field-photo-wet-crop-2025-202608261615.csv"},
}


def baseline_connection():
    paths = {t: {s: _DIR / name for s, name in m.items()} for t, m in BASELINE_SOURCES.items()}
    missing = [p.name for m in paths.values() for p in m.values() if not p.exists()]
    if missing:
        pytest.skip(f"baseline export files no longer present: {missing}")
    con = csv_adapter.get_connection()
    csv_adapter.load_lots(con, paths["fields"])
    csv_adapter.load_diaries(con, paths["diaries"])
    csv_adapter.load_photos(con, paths["photos"])
    csv_adapter.load_fertilizer_applications(con, paths["diaries"])
    return con
