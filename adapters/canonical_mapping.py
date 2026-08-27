"""Column-name mapping from raw (PII-stripped) source columns to the
canonical validation model.

The real export uses `field_id` as the join key across all sources (per
project instruction), which becomes canonical `lot_id`. `geojson` columns
actually contain WKT strings, not GeoJSON (verified against the sample
data), so they're mapped to `geometry_wkt` rather than `geometry_geojson`.
Area is reported in square meters and converted to hectares.
"""

GEOMETRY_CRS = "EPSG:4326"

SQM_PER_HA = 10_000

FIELDS_RENAME = {
    "field_id": "lot_id",
    "participant_id": "farmer_id",
    "unique_name": "unique_name",
    "group_id": "group_id",
    "geojson": "geometry_wkt",
    "tenurial_status": "tenurial_status",
    "field_area_self_reported_sqm": "declared_area_sqm",
    "field_area_from_geojson_sqm": "geojson_area_sqm_reported",
    "region_id": "region_id",
    "area_id": "area_id",
    "is_validated": "is_validated",
    "physical_field_id": "physical_field_id",
    "irrisystem": "irrigation_system",
    "ia": "irrigators_association",
    "tsag": "tsag",
}

DIARIES_RENAME = {
    "field_diary_id": "diary_id",
    "field_id": "lot_id",
    "planting_date": "planting_date",
    "straw_management_date": "straw_management_date",
    "harvest_date": "harvest_date",
    "crop": "crop",
}

PHOTOS_RENAME = {
    "photo_id": "photo_id",
    "field_id": "lot_id",
    "season_id": "season_id",
    "date_time": "capture_date",
    "category": "category",
    "status": "status",
    "latitude": "latitude",
    "longitude": "longitude",
}

FERTILIZER_RENAME = {
    "field_fertilizer_application_id": "application_id",
    "field_id": "lot_id",
    "fertilizer_type_id": "fertilizer_type_id",
    "applied_date": "applied_date",
    "applied_amount_kg": "applied_amount_kg",
}
