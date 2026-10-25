"""Loads the real filtered CSV export into canonical DuckDB tables.

Applies, in order: PII column stripping (adapters.pii_policy), the
`is_deleted = false` filter, column renaming to the canonical model
(adapters.canonical_mapping), season_id injection (the raw fields/diaries
files don't carry a season_id column - it's implied by which file a row
came from), de-duplication of the diary fan-out caused by the source join
with fertilizer applications, and exclusion of photos with no `field_id`
(unmatched / "Pending Match" photos with no lot to attach to).

No data is fabricated: only the tables backed by a real CSV are populated.
`farmers`, `contracts`, `riceid`, `lipa`, and `seasons` are intentionally
absent from this loader.
"""

import re
from pathlib import Path

import duckdb

from adapters.canonical_mapping import (
    DIARIES_RENAME,
    FERTILIZER_RENAME,
    FIELDS_RENAME,
    GEOMETRY_CRS,
    PHOTOS_RENAME,
    SQM_PER_HA,
)
from adapters.pii_policy import (
    DIARIES_ALLOWED_COLUMNS,
    FERTILIZER_ALLOWED_COLUMNS,
    FIELDS_ALLOWED_COLUMNS,
    PHOTOS_ALLOWED_COLUMNS,
)

DATA_ROOT = Path(__file__).resolve().parents[1] / "data"

# Each region has its own data/<region>/csv export directory. New regions
# just need a folder here - no code change - as long as filenames follow
# the region's naming convention below.
REGIONS = ("pangasinan", "cagayan")
DEFAULT_REGION = "pangasinan"

# region -> {season_id: filename season code}, used to find that season's
# file within the region's csv dir. Each region is pinned to the catalog
# seasons (see catalog/season_bounds.yaml) its data actually covers. The
# code must be specific enough to tell seasons apart in a filename:
# Pangasinan's export names files "...-dry-crop-2025-..." / "...-wet-crop-2025-..."
# / "...-dry-crop-2026-..." (the year matters - "dry-crop" alone would match
# both 2025 and 2026); Cagayan's uses "ds2026"/"ws2026" ("dry/wet season 2026").
# Season 5 (Dry Crop 2026) is one catalog season shared by both regions -
# each region's data is still scoped to its own files and results store.
_REGION_SEASON_TAGS = {
    "pangasinan": {3: "dry-crop-2025", 4: "wet-crop-2025", 5: "dry-crop-2026"},
    "cagayan": {5: "ds2026", 6: "ws2026"},
}

# region -> table -> filename prefix template(s) (with a `{tag}` placeholder
# for the season code above). Each region's export uses a different naming
# convention, so these are looked up per region rather than shared. A table
# may list several templates when exports of the same season were named
# inconsistently (e.g. Pangasinan photos: "field-photo-" vs "field-photos-");
# all of them compete equally - see _latest_match.
_REGION_SOURCE_PATTERNS = {
    "pangasinan": {
        "fields": ["fields-{tag}-"],
        "diaries": ["field-diaries-{tag}-"],
        "photos": ["field-photo-{tag}-", "field-photos-{tag}-"],
    },
    "cagayan": {
        "fields": ["field-{tag}-cagayan-"],
        "diaries": ["field-diary-{tag}-cagayan-"],
        "photos": ["field-photo-{tag}-cagayan-"],
    },
}


def region_csv_dir(region: str) -> Path:
    return DATA_ROOT / region / "csv"


def region_season_ids(region: str) -> list[int]:
    """The catalog season_ids (see catalog/season_bounds.yaml) this region's
    data is scoped to, e.g. [5, 6] (Dry/Wet Crop 2026) for Cagayan."""
    return list(_REGION_SEASON_TAGS.get(region, _REGION_SEASON_TAGS[DEFAULT_REGION]))


# Every export filename ends in a 12-digit export timestamp (yyyymmddHHMM).
_EXPORT_TIMESTAMP_RE = re.compile(r"-(\d{12})\.csv$")


def _export_sort_key(path: Path) -> tuple[str, float, str]:
    """Newest export wins: the timestamp in the filename first (the export
    time, independent of copy/download times), then file mtime, then name as
    a deterministic tie-breaker."""
    match = _EXPORT_TIMESTAMP_RE.search(path.name)
    return (match.group(1) if match else "", path.stat().st_mtime, path.name)


def _latest_match(directory: Path, prefixes: list[str] | str) -> Path | None:
    """The most recent export among ALL files matching ANY of `prefixes`.
    Naming variants (e.g. "field-photo-" vs "field-photos-") are compared on
    export time, not on which pattern is listed first, so re-exporting a
    season under a slightly different name still supersedes the old file."""
    if isinstance(prefixes, str):
        prefixes = [prefixes]
    candidates = {path for prefix in prefixes for path in directory.glob(f"{prefix}*.csv")}
    return max(candidates, key=_export_sort_key) if candidates else None


def _sources_for(region: str, table: str) -> dict[int, Path]:
    """Returns only the season_ids that actually have a matching file for
    `table` ("fields", "diaries", or "photos") in this region - a region
    missing a season's export (e.g. Cagayan before its wet-season 2026 data
    lands) simply omits that season_id. When a season has several exports,
    the newest one is used (see _latest_match)."""
    directory = region_csv_dir(region)
    season_tags = _REGION_SEASON_TAGS.get(region, _REGION_SEASON_TAGS[DEFAULT_REGION])
    patterns = _REGION_SOURCE_PATTERNS.get(region, _REGION_SOURCE_PATTERNS[DEFAULT_REGION])[table]
    sources: dict[int, Path] = {}
    for season_id, tag in season_tags.items():
        match = _latest_match(directory, [template.format(tag=tag) for template in patterns])
        if match is not None:
            sources[season_id] = match
    return sources


def source_fingerprint(region: str = DEFAULT_REGION) -> tuple:
    """Identity of the exact files currently selected for a region (names +
    mtimes + sizes). Callers that cache the loaded database key on this so a
    newly dropped export is picked up instead of serving stale data."""
    files = sorted(
        {
            path
            for table in ("fields", "diaries", "photos")
            for path in _sources_for(region, table).values()
        }
    )
    return tuple((p.name, p.stat().st_mtime_ns, p.stat().st_size) for p in files)


def fields_sources(region: str = DEFAULT_REGION) -> dict[int, Path]:
    return _sources_for(region, "fields")


def diaries_sources(region: str = DEFAULT_REGION) -> dict[int, Path]:
    return _sources_for(region, "diaries")


def photos_sources(region: str = DEFAULT_REGION) -> dict[int, Path]:
    return _sources_for(region, "photos")


def fertilizer_sources(region: str = DEFAULT_REGION) -> dict[int, Path]:
    # Same source file as diaries_sources: applied_date/fertilizer_type_id/
    # etc. live in the diary fan-out that load_diaries de-duplicates away,
    # and each row is distinct once field_fertilizer_application_id is
    # included.
    return diaries_sources(region)


# Back-compat module-level constants (default region), used by tests and
# scripts that don't care about region selection.
FIELDS_SOURCES = fields_sources()
DIARIES_SOURCES = diaries_sources()
PHOTOS_SOURCES = photos_sources()
FERTILIZER_SOURCES = fertilizer_sources()


def get_connection(database: str = ":memory:") -> duckdb.DuckDBPyConnection:
    return duckdb.connect(database)


def _select_allowed(allowed_columns: list[str], rename: dict[str, str] | None = None) -> str:
    rename = rename or {}
    parts = []
    for col in allowed_columns:
        target = rename.get(col, col)
        parts.append(f'"{col}" AS "{target}"' if target != col else f'"{col}"')
    return ", ".join(parts)


_EMPTY_LOTS_SQL = """
    SELECT
        CAST(NULL AS VARCHAR) AS lot_id, CAST(NULL AS INTEGER) AS season_id,
        CAST(NULL AS VARCHAR) AS farmer_id, CAST(NULL AS VARCHAR) AS unique_name,
        CAST(NULL AS VARCHAR) AS group_id, CAST(NULL AS VARCHAR) AS geometry_wkt,
        CAST(NULL AS VARCHAR) AS geometry_crs, CAST(NULL AS VARCHAR) AS tenurial_status,
        CAST(NULL AS DOUBLE) AS declared_area_ha, CAST(NULL AS DOUBLE) AS geojson_area_ha_reported,
        CAST(NULL AS VARCHAR) AS region_id, CAST(NULL AS VARCHAR) AS area_id,
        CAST(NULL AS VARCHAR) AS is_validated, CAST(NULL AS VARCHAR) AS physical_field_id,
        CAST(NULL AS VARCHAR) AS irrigation_system, CAST(NULL AS VARCHAR) AS irrigators_association,
        CAST(NULL AS VARCHAR) AS tsag
    WHERE 1 = 0
"""


def load_lots(con: duckdb.DuckDBPyConnection, sources: dict[int, Path] | None = None) -> None:
    sources = FIELDS_SOURCES if sources is None else sources
    if not sources:
        con.execute(f"CREATE OR REPLACE TABLE lots AS {_EMPTY_LOTS_SQL}")
        return
    select_cols = _select_allowed(FIELDS_ALLOWED_COLUMNS, FIELDS_RENAME)
    unions = []
    for season_id, path in sources.items():
        unions.append(
            f"""
            SELECT {select_cols}, {season_id} AS season_id
            FROM read_csv_auto('{path.as_posix()}', ALL_VARCHAR=TRUE)
            WHERE lower("is_deleted") = 'false'
            """
        )
    union_sql = " UNION ALL ".join(unions)
    con.execute(
        f"""
        CREATE OR REPLACE TABLE lots AS
        SELECT
            lot_id,
            season_id,
            farmer_id,
            unique_name,
            group_id,
            geometry_wkt,
            '{GEOMETRY_CRS}' AS geometry_crs,
            tenurial_status,
            TRY_CAST(declared_area_sqm AS DOUBLE) / {SQM_PER_HA} AS declared_area_ha,
            TRY_CAST(geojson_area_sqm_reported AS DOUBLE) / {SQM_PER_HA} AS geojson_area_ha_reported,
            region_id,
            area_id,
            is_validated,
            physical_field_id,
            irrigation_system,
            irrigators_association,
            tsag
        FROM ({union_sql})
        """
    )


_EMPTY_DIARIES_SQL = """
    SELECT
        CAST(NULL AS VARCHAR) AS diary_id, CAST(NULL AS VARCHAR) AS lot_id,
        CAST(NULL AS INTEGER) AS season_id, CAST(NULL AS DATE) AS planting_date,
        CAST(NULL AS DATE) AS straw_management_date, CAST(NULL AS DATE) AS harvest_date,
        CAST(NULL AS VARCHAR) AS crop
    WHERE 1 = 0
"""


def load_diaries(con: duckdb.DuckDBPyConnection, sources: dict[int, Path] | None = None) -> None:
    sources = DIARIES_SOURCES if sources is None else sources
    if not sources:
        con.execute(f"CREATE OR REPLACE TABLE diaries AS {_EMPTY_DIARIES_SQL}")
        return
    select_cols = _select_allowed(DIARIES_ALLOWED_COLUMNS, DIARIES_RENAME)
    unions = []
    for season_id, path in sources.items():
        unions.append(
            f"""
            SELECT DISTINCT {select_cols}, {season_id} AS season_id
            FROM read_csv_auto('{path.as_posix()}', ALL_VARCHAR=TRUE)
            """
        )
    union_sql = " UNION ALL ".join(unions)
    con.execute(
        f"""
        CREATE OR REPLACE TABLE diaries AS
        SELECT
            diary_id,
            lot_id,
            season_id,
            TRY_CAST(planting_date AS DATE) AS planting_date,
            TRY_CAST(straw_management_date AS DATE) AS straw_management_date,
            TRY_CAST(harvest_date AS DATE) AS harvest_date,
            crop
        FROM ({union_sql})
        """
    )


_EMPTY_PHOTOS_SQL = """
    SELECT
        CAST(NULL AS VARCHAR) AS photo_id, CAST(NULL AS VARCHAR) AS lot_id,
        CAST(NULL AS INTEGER) AS season_id, CAST(NULL AS TIMESTAMP) AS capture_date,
        CAST(NULL AS VARCHAR) AS category, CAST(NULL AS VARCHAR) AS status,
        CAST(NULL AS DOUBLE) AS latitude, CAST(NULL AS DOUBLE) AS longitude
    WHERE 1 = 0
"""


def load_photos(con: duckdb.DuckDBPyConnection, sources: dict[int, Path] | None = None) -> None:
    sources = PHOTOS_SOURCES if sources is None else sources
    if not sources:
        con.execute(f"CREATE OR REPLACE TABLE photos AS {_EMPTY_PHOTOS_SQL}")
        return
    # season_id is a source-system internal id and isn't guaranteed to line
    # up with our catalog season_ids (e.g. Cagayan's raw export reports "9"
    # for every row of its Dry Crop 2026 file) - so, like lots/diaries, it's
    # overridden here with the season_id implied by which file the row came
    # from rather than trusted from the raw column.
    select_cols = _select_allowed(
        [c for c in PHOTOS_ALLOWED_COLUMNS if c != "season_id"],
        PHOTOS_RENAME,
    )
    unions = []
    for season_id, path in sources.items():
        unions.append(
            f"""
            SELECT {select_cols}, {season_id} AS season_id
            FROM read_csv_auto('{path.as_posix()}', ALL_VARCHAR=TRUE)
            WHERE lower("is_deleted") = 'false'
              AND "field_id" IS NOT NULL AND "field_id" != ''
            """
        )
    union_sql = " UNION ALL ".join(unions)
    con.execute(
        f"""
        CREATE OR REPLACE TABLE photos AS
        SELECT
            photo_id,
            lot_id,
            season_id,
            TRY_STRPTIME(capture_date, '%Y-%m-%d %H:%M:%S.%g %z') AS capture_date,
            category,
            status,
            TRY_CAST(latitude AS DOUBLE) AS latitude,
            TRY_CAST(longitude AS DOUBLE) AS longitude
        FROM ({union_sql})
        """
    )


_EMPTY_FERTILIZER_SQL = """
    SELECT
        CAST(NULL AS BIGINT) AS application_id, CAST(NULL AS VARCHAR) AS lot_id,
        CAST(NULL AS INTEGER) AS season_id, CAST(NULL AS VARCHAR) AS fertilizer_type_id,
        CAST(NULL AS DATE) AS applied_date, CAST(NULL AS DOUBLE) AS applied_amount_kg
    WHERE 1 = 0
"""


def load_fertilizer_applications(con: duckdb.DuckDBPyConnection, sources: dict[int, Path] | None = None) -> None:
    sources = FERTILIZER_SOURCES if sources is None else sources
    if not sources:
        con.execute(f"CREATE OR REPLACE TABLE fertilizer_applications AS {_EMPTY_FERTILIZER_SQL}")
        return
    select_cols = _select_allowed(FERTILIZER_ALLOWED_COLUMNS, FERTILIZER_RENAME)
    unions = []
    for season_id, path in sources.items():
        unions.append(
            f"""
            SELECT DISTINCT {select_cols}, {season_id} AS season_id
            FROM read_csv_auto('{path.as_posix()}', ALL_VARCHAR=TRUE)
            """
        )
    union_sql = " UNION ALL ".join(unions)
    con.execute(
        f"""
        CREATE OR REPLACE TABLE fertilizer_applications AS
        SELECT
            TRY_CAST(application_id AS BIGINT) AS application_id,
            lot_id,
            season_id,
            fertilizer_type_id,
            TRY_CAST(applied_date AS DATE) AS applied_date,
            TRY_CAST(applied_amount_kg AS DOUBLE) AS applied_amount_kg
        FROM ({union_sql})
        """
    )


def load_all(con: duckdb.DuckDBPyConnection, region: str = DEFAULT_REGION) -> None:
    load_lots(con, fields_sources(region))
    load_diaries(con, diaries_sources(region))
    load_photos(con, photos_sources(region))
    load_fertilizer_applications(con, fertilizer_sources(region))


if __name__ == "__main__":
    conn = get_connection()
    load_all(conn)
    for table in ("lots", "diaries", "photos", "fertilizer_applications"):
        count = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
        print(f"{table}: {count} rows")
    print(conn.execute("SELECT * FROM lots LIMIT 3").fetchdf())
