import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import streamlit as st

from catalog.loader import season_labels
from adapters import csv_adapter
from adapters.pii_policy import (
    DIARIES_ALLOWED_COLUMNS,
    FERTILIZER_ALLOWED_COLUMNS,
    FIELDS_ALLOWED_COLUMNS,
    PHOTOS_ALLOWED_COLUMNS,
)
from app.components.charts import geometry_coverage_chart
from app.components.ui import card, chip, kpi_row, page_header, section
from app.components.state import (
    current_region,
    field_season_readiness_df,
    get_data_connection,
    results_df,
    run_validation,
)

page_header(
    "Data & Setup",
    "Choose the seasons to validate and run the deterministic C1-C9 rules. No LLM is used on this page.",
    eyebrow="Step 1 · Validate",
    chips=[chip(current_region().title(), "brand", dot=True), chip("PII-stripped", "good", dot=True)],
)

REGION = current_region()
FIELDS_SOURCES = csv_adapter.fields_sources(REGION)
DIARIES_SOURCES = csv_adapter.diaries_sources(REGION)
PHOTOS_SOURCES = csv_adapter.photos_sources(REGION)
FERTILIZER_SOURCES = csv_adapter.fertilizer_sources(REGION)

ALL_SEASON_LABELS = season_labels()
# Each region is scoped to its own catalog seasons (see
# adapters.csv_adapter.region_season_ids and catalog/season_bounds.yaml) -
# Cagayan only ever offers Dry/Wet Crop 2026, Pangasinan only Dry/Wet Crop
# 2025, regardless of which other seasons are documented in the catalog.
REGION_SEASON_IDS = {str(season_id) for season_id in csv_adapter.region_season_ids(REGION)}
SEASON_LABELS = {
    season_id: label for season_id, label in ALL_SEASON_LABELS.items() if season_id in REGION_SEASON_IDS
}
LABEL_TO_SEASON_ID = {label: season_id for season_id, label in SEASON_LABELS.items()}
# Only seasons with a real lots CSV (see adapters/csv_adapter.py) can
# actually be validated - the rest are season_bounds.yaml entries kept for
# when that data arrives (see catalog/season_bounds.yaml's own comment).
ACTIVE_SEASON_IDS = {str(season_id) for season_id in FIELDS_SOURCES}
con = get_data_connection()

with card("run"):
    section("Run validation", "Is this monitoring dataset ready for verification?")

    row_cols = st.columns([1] * len(SEASON_LABELS) + [1.3, 1.6])
    season_cols, run_col, status_col = row_cols[:-2], row_cols[-2], row_cols[-1]

    selected_labels = []
    for col, (season_id, label) in zip(season_cols, SEASON_LABELS.items()):
        with col:
            is_active = season_id in ACTIVE_SEASON_IDS
            checked = st.checkbox(
                label,
                key=f"season_checkbox_{season_id}",
                disabled=not is_active,
                help=None if is_active else "No data loaded for this season yet.",
            )
            if checked:
                selected_labels.append(label)

    with run_col:
        run_clicked = st.button("Run Data Validation", type="primary", disabled=not selected_labels)

    with status_col:
        run_id = st.session_state.get("validation_run_id")
        if not selected_labels:
            st.caption(":orange[Select a season first]")
        elif run_id:
            st.caption(f"Last run: `{run_id}`")
        else:
            st.caption("No run yet")

    if run_clicked:
        season_ids = [LABEL_TO_SEASON_ID[label] for label in selected_labels]
        with st.spinner("Running deterministic validation and preparing Dashboard + Field Review..."):
            run_id = run_validation(season_ids=season_ids)
            # Pre-warm the cached aggregates (keyed by this run_id) that both
            # the Dashboard and Field Review read, so the spinner doesn't
            # release until there's actually something to show on either -
            # not just until the batch engine finishes.
            readiness_df = field_season_readiness_df(run_id)
            detail_df = results_df(run_id)
        st.session_state["validation_run_id"] = run_id
        st.success(f"Validation run complete: {run_id} ({len(detail_df):,} results, {len(readiness_df):,} field-seasons)")

section("Loaded sources", "Rows kept after dropping deleted records; columns follow a PII allowlist.")
sources = [
    ("lots", FIELDS_SOURCES, FIELDS_ALLOWED_COLUMNS),
    ("diaries", DIARIES_SOURCES, DIARIES_ALLOWED_COLUMNS),
    ("photos", PHOTOS_SOURCES, PHOTOS_ALLOWED_COLUMNS),
    ("fertilizer_applications", FERTILIZER_SOURCES, FERTILIZER_ALLOWED_COLUMNS),
]
source_cols = st.columns(4)
for col, (table, source_map, allowed_columns) in zip(source_cols, sources):
    with col:
        with card(f"src_{table}"):
            st.markdown(f"**`{table}`**")
            for season_id, path in source_map.items():
                label = SEASON_LABELS.get(str(season_id), str(season_id))
                st.markdown(
                    f'<div class="src"><span class="src-l">{label}</span>'
                    f'<span class="src-f" title="{path.name}">{path.name}</span></div>',
                    unsafe_allow_html=True,
                )
            row_count = con.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            st.metric("Rows (is_deleted=false)", f"{row_count:,}")
            with st.expander("Allowed columns"):
                st.caption(", ".join(allowed_columns))

section("Data not present in this dataset")
st.info(
    "`farmers`, `contracts`, `riceid`, and `lipa` sources are not part of this export, "
    "and no active rule (C1-C9) depends on them - they're documented in the catalog "
    "schema only so a future rule referencing them is recognized as legitimate rather "
    "than hallucinated. Season date boundaries (used by C4/C7) come from the editable "
    "config in `catalog/season_bounds.yaml`, not from a seasons.csv."
)

cov_col, health_col = st.columns([1, 1])

with cov_col, card("coverage"):
    section("Field-season coverage")
    coverage = con.execute(
        """
        SELECT season_id, COUNT(*) AS field_seasons,
               SUM(CASE WHEN geometry_wkt IS NOT NULL THEN 1 ELSE 0 END) AS has_geometry
        FROM lots GROUP BY 1 ORDER BY 1
        """
    ).fetchdf()
    coverage["season_id"] = coverage["season_id"].astype(int).astype(str).map(lambda s: SEASON_LABELS.get(s, s))
    st.altair_chart(geometry_coverage_chart(coverage), use_container_width=True)

with health_col, card("health"):
    section("Source-data health")
    health = con.execute(
        """
        SELECT
          (SELECT COUNT(*) FROM lots WHERE declared_area_ha IS NULL) AS lots_missing_declared_area,
          (SELECT COUNT(*) FROM lots WHERE geometry_wkt IS NULL) AS lots_missing_geometry,
          (SELECT COUNT(*) FROM diaries) AS diaries_with_data,
          (SELECT COUNT(DISTINCT lot_id || '-' || season_id) FROM lots) - (SELECT COUNT(*) FROM diaries) AS lots_without_diary,
          (SELECT COUNT(*) FROM photos) AS photos_with_data
        """
    ).fetchdf().iloc[0]
    hh1, hh2 = st.columns(2)
    hh1.metric("Lots missing declared area", f"{health['lots_missing_declared_area']:,}")
    hh2.metric("Lots missing geometry", f"{health['lots_missing_geometry']:,}")
    hh3, hh4 = st.columns(2)
    hh3.metric("Diaries with data", f"{health['diaries_with_data']:,}")
    hh4.metric("Lots without a diary", f"{health['lots_without_diary']:,}")
    st.metric("Photos with data", f"{health['photos_with_data']:,}")
