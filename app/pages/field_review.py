import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import pandas as pd
import streamlit as st

from catalog.loader import season_labels
from app.components.charts import readiness_status_bar
from app.components.copilot_ui import render_copilot_launcher
from app.components.exports import detailed_export_df, field_summary_export_df
from app.components.state import field_season_readiness_df, get_rules, lots_attributes_df, results_df

title_col, copilot_col = st.columns([5, 1])
with title_col:
    st.title("Field Review")
with copilot_col:
    render_copilot_launcher()
st.caption("Deterministic, local CSV generation - no LLM is used on this page.")

SEASON_LABELS = season_labels()
LABEL_TO_SEASON_ID = {label: season_id for season_id, label in SEASON_LABELS.items()}

# Session-scoped, not the persisted store's latest run - see Dashboard for why.
run_id = st.session_state.get("validation_run_id")
if run_id is None:
    st.info("No validation run yet. Go to **Data & Setup** to select seasons and click Run Data Validation.")
    st.stop()

detail_df = results_df(run_id)
readiness_df = field_season_readiness_df(run_id).merge(lots_attributes_df(), on=["lot_id", "season_id"], how="left")
rules = {r.rule_id: r for r in get_rules(validate=False)}

st.subheader("Filters")
c1, c2, c3 = st.columns(3)
with c1:
    # Fixed key so the Copilot page can pre-set this filter (st.session_state
    # written before this widget renders) via an "Open in Field Review" link.
    rule_filter = st.multiselect("Rule", sorted(detail_df["rule_id"].unique()), key="field_review_rule_filter")
with c2:
    readiness_filter = st.multiselect("Readiness", sorted(readiness_df["readiness"].unique()))
with c3:
    season_options = sorted(detail_df["season_id"].unique(), key=lambda s: int(s))
    season_label_filter = st.multiselect("Season", [SEASON_LABELS.get(s, s) for s in season_options])
    season_filter = [LABEL_TO_SEASON_ID.get(label, label) for label in season_label_filter]

st.caption("Filter by field identity (instead of the raw field_id):")
d1, d2, d3, d4 = st.columns(4)
with d1:
    field_name_filter = st.text_input("Field name contains")
with d2:
    tsag_filter = st.multiselect("TSAG", sorted(readiness_df["tsag"].dropna().unique()))
with d3:
    ia_filter = st.multiselect("IA", sorted(readiness_df["ia"].dropna().unique()))
with d4:
    ris_filter = st.multiselect("RIS", sorted(readiness_df["ris"].dropna().unique()))

st.caption("Filter by how many rules failed / need review, per field-season:")
e1, e2 = st.columns(2)
max_fail_count = int(readiness_df["fail_count"].max()) if not readiness_df.empty else 0
max_review_count = int(readiness_df["review_count"].max()) if not readiness_df.empty else 0
with e1:
    min_fail_filter = st.number_input("Min failures", min_value=0, max_value=max(max_fail_count, 0), value=0, step=1)
with e2:
    min_review_filter = st.number_input(
        "Min NEEDS_REVIEW rules", min_value=0, max_value=max(max_review_count, 0), value=0, step=1
    )

filtered = detail_df.copy()
if rule_filter:
    filtered = filtered[filtered["rule_id"].isin(rule_filter)]
if season_filter:
    filtered = filtered[filtered["season_id"].isin(season_filter)]

lot_level_filtered = readiness_df.copy()
if readiness_filter:
    lot_level_filtered = lot_level_filtered[lot_level_filtered["readiness"].isin(readiness_filter)]
if min_fail_filter:
    lot_level_filtered = lot_level_filtered[lot_level_filtered["fail_count"] >= min_fail_filter]
if min_review_filter:
    lot_level_filtered = lot_level_filtered[lot_level_filtered["review_count"] >= min_review_filter]
if field_name_filter:
    lot_level_filtered = lot_level_filtered[
        lot_level_filtered["field_name"].str.contains(field_name_filter, case=False, na=False)
    ]
if tsag_filter:
    lot_level_filtered = lot_level_filtered[lot_level_filtered["tsag"].isin(tsag_filter)]
if ia_filter:
    lot_level_filtered = lot_level_filtered[lot_level_filtered["ia"].isin(ia_filter)]
if ris_filter:
    lot_level_filtered = lot_level_filtered[lot_level_filtered["ris"].isin(ris_filter)]

filtered_keys = (filtered["lot_id"] + "\x1f" + filtered["season_id"]).unique()
lot_level_keys = (lot_level_filtered["lot_id"] + "\x1f" + lot_level_filtered["season_id"]).unique()
readiness_keys = readiness_df["lot_id"] + "\x1f" + readiness_df["season_id"]
readiness_filtered = readiness_df[readiness_keys.isin(filtered_keys) & readiness_keys.isin(lot_level_keys)].copy()
readiness_filtered["season"] = readiness_filtered["season_id"].map(lambda s: SEASON_LABELS.get(s, s))

st.subheader(f"Field-seasons matching filters: {len(readiness_filtered):,}")
if not readiness_filtered.empty:
    st.altair_chart(readiness_status_bar(readiness_filtered), use_container_width=True)
st.dataframe(
    readiness_filtered[
        [
            "lot_id",
            "field_name",
            "tsag",
            "ia",
            "ris",
            "season",
            "readiness",
            "fail_count",
            "review_count",
            "fail_rule_ids",
            "review_rule_ids",
        ]
    ].rename(columns={"lot_id": "field_id", "field_name": "field_name (lot name)", "ia": "IA", "ris": "RIS", "tsag": "TSAG"}),
    use_container_width=True,
    hide_index=True,
)

st.subheader("Select a field-season for detail")
options = list(zip(readiness_filtered["lot_id"], readiness_filtered["season_id"]))
name_lookup = dict(zip(zip(readiness_filtered["lot_id"], readiness_filtered["season_id"]), readiness_filtered["field_name"]))
if options:
    selected = st.selectbox(
        "Field",
        options,
        format_func=lambda t: f"{name_lookup.get(t) or t[0]} ({SEASON_LABELS.get(t[1], t[1])})",
    )
    if selected:
        lot_id, season_id = selected
        detail_rows = detail_df[(detail_df["lot_id"] == lot_id) & (detail_df["season_id"] == season_id)]
        readiness_row = readiness_df[(readiness_df["lot_id"] == lot_id) & (readiness_df["season_id"] == season_id)]
        st.write(f"**Overall readiness:** {readiness_row['readiness'].iloc[0]}")
        for _, row in detail_rows.sort_values("rule_id").iterrows():
            rule = rules.get(row["rule_id"])
            with st.expander(f"{row['rule_id']} - {rule.name if rule else ''} - {row['result']}"):
                st.write("**Reason:**", row["reason"])
                st.write("**Observations:**", json.loads(row["observations"]))
                missing_inputs = json.loads(row["missing_inputs"]) if row["missing_inputs"] else []
                if missing_inputs:
                    st.warning("**Missing data driving this result:** " + ", ".join(missing_inputs))
                if rule:
                    st.write("**Rule description:**", rule.description)

st.divider()
st.subheader("CSV export")
st.caption("Exports respect the active filters above. Choose Full Run to ignore filters.")

export_scope = st.radio("Scope", ["Filtered results", "Full current validation run"], horizontal=True)
export_df = detail_df if export_scope == "Full current validation run" else filtered
export_readiness = readiness_df if export_scope == "Full current validation run" else readiness_filtered

col1, col2 = st.columns(2)
with col1:
    st.download_button(
        "Download Field Summary Export (CSV)",
        field_summary_export_df(export_readiness, SEASON_LABELS).to_csv(index=False).encode("utf-8"),
        file_name=f"field_summary_{run_id}.csv",
        mime="text/csv",
        type="primary",
    )
with col2:
    st.download_button(
        "Download Detailed Validation Export (CSV)",
        detailed_export_df(export_df, lots_attributes_df(), SEASON_LABELS).to_csv(index=False).encode("utf-8"),
        file_name=f"detailed_validation_{run_id}.csv",
        mime="text/csv",
        type="primary",
    )
