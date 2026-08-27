"""Explicit column allowlists for each raw source table.

Only columns listed here are ever read out of the raw CSV exports and into
the canonical validation database. This is an allowlist, not a denylist, so
an unrecognized new column in a future export is excluded by default rather
than silently leaking through.

Columns deliberately excluded as PII: `owner_name` (farmer's name) and
`rice_specialist` (staff member's name) on the fields source. `taken_by_user_id`
/ `reviewed_by_user_id` / `reviewed_by_user_account_id` on the photos source
are excluded too since they identify individual staff accounts and are not
needed by C1-C9.
"""

FIELDS_ALLOWED_COLUMNS = [
    "field_id",
    "participant_id",
    "unique_name",
    "group_id",
    "geojson",
    "tenurial_status",
    "field_area_self_reported_sqm",
    "field_area_from_geojson_sqm",
    "region_id",
    "area_id",
    "is_validated",
    "physical_field_id",
    "irrisystem",
    "ia",
    "tsag",
    "is_deleted",
]

DIARIES_ALLOWED_COLUMNS = [
    "field_diary_id",
    "field_id",
    "planting_date",
    "straw_management_date",
    "harvest_date",
    "crop",
]

PHOTOS_ALLOWED_COLUMNS = [
    "photo_id",
    "field_id",
    "season_id",
    "date_time",
    "category",
    "status",
    "latitude",
    "longitude",
    "is_deleted",
]

FERTILIZER_ALLOWED_COLUMNS = [
    "field_fertilizer_application_id",
    "field_id",
    "fertilizer_type_id",
    "applied_date",
    "applied_amount_kg",
]
