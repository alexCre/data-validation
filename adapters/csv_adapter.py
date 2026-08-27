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

DATA_DIR = Path(__file__).resolve().parents[1] / "data" / "csv"

# season_id -> source file. Only what's actually present in the export.
FIELDS_SOURCES = {
    3: DATA_DIR / "fields-dry-crop-2025-202608241808.csv",
    4: DATA_DIR / "fields-wet-crop-2025-202608241809.csv",
}
DIARIES_SOURCES = {
    3: DATA_DIR / "field-diaries-dry-crop-2025-202608241811.csv",
    4: DATA_DIR / "field-diaries-wet-crop-2025-202608261648.csv",
}
PHOTOS_SOURCES = {
    3: DATA_DIR / "field-photos-dry-crop-2025-202608241816.csv",
    4: DATA_DIR / "field-photo-wet-crop-2025-202608261615.csv",
}
# Same source file as DIARIES_SOURCES: applied_date/fertilizer_type_id/etc.
# live in the diary fan-out that load_diaries de-duplicates away, and each
# row is distinct once field_fertilizer_application_id is included.
FERTILIZER_SOURCES = DIARIES_SOURCES


def get_connection(database: str = ":memory:") -> duckdb.DuckDBPyConnection:
    return duckdb.connect(database)


def _select_allowed(allowed_columns: list[str], rename: dict[str, str] | None = None) -> str:
    rename = rename or {}
    parts = []
    for col in allowed_columns:
        target = rename.get(col, col)
        parts.append(f'"{col}" AS "{target}"' if target != col else f'"{col}"')
    return ", ".join(parts)


def load_lots(con: duckdb.DuckDBPyConnection) -> None:
    select_cols = _select_allowed(FIELDS_ALLOWED_COLUMNS, FIELDS_RENAME)
    unions = []
    for season_id, path in FIELDS_SOURCES.items():
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


def load_diaries(con: duckdb.DuckDBPyConnection) -> None:
    select_cols = _select_allowed(DIARIES_ALLOWED_COLUMNS, DIARIES_RENAME)
    unions = []
    for season_id, path in DIARIES_SOURCES.items():
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


def load_photos(con: duckdb.DuckDBPyConnection) -> None:
    select_cols = _select_allowed(PHOTOS_ALLOWED_COLUMNS, PHOTOS_RENAME)
    unions = []
    for season_id, path in PHOTOS_SOURCES.items():
        unions.append(
            f"""
            SELECT {select_cols}
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
            TRY_CAST(season_id AS INTEGER) AS season_id,
            TRY_STRPTIME(capture_date, '%Y-%m-%d %H:%M:%S.%g %z') AS capture_date,
            category,
            status,
            TRY_CAST(latitude AS DOUBLE) AS latitude,
            TRY_CAST(longitude AS DOUBLE) AS longitude
        FROM ({union_sql})
        """
    )


def load_fertilizer_applications(con: duckdb.DuckDBPyConnection) -> None:
    select_cols = _select_allowed(FERTILIZER_ALLOWED_COLUMNS, FERTILIZER_RENAME)
    unions = []
    for season_id, path in FERTILIZER_SOURCES.items():
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


def load_all(con: duckdb.DuckDBPyConnection) -> None:
    load_lots(con)
    load_diaries(con)
    load_photos(con)
    load_fertilizer_applications(con)


if __name__ == "__main__":
    conn = get_connection()
    load_all(conn)
    for table in ("lots", "diaries", "photos", "fertilizer_applications"):
        count = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
        print(f"{table}: {count} rows")
    print(conn.execute("SELECT * FROM lots LIMIT 3").fetchdf())
