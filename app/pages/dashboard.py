import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import pandas as pd
import streamlit as st

from catalog.loader import season_labels
from app.components.charts import (
    horizontal_magnitude_bar,
    readiness_status_bar,
    rule_sort_key,
    SEQUENTIAL_BLUE,
    STATUS_CRITICAL,
    STATUS_WARNING,
)
from app.components.state import field_season_readiness_df, get_rules, results_df

st.title("Dashboard")

SEASON_LABELS = season_labels()  # {"3": "Dry Crop 2025", "4": "Wet Crop 2025"}

# Session-scoped, not the persisted store's latest run - the app should
# start empty (no Dashboard/Field Review content) until Run Data Validation
# is clicked on the Data & Setup page in this session, even if a prior run
# exists on disk.
run_id = st.session_state.get("validation_run_id")
if run_id is None:
    st.info("No validation run yet. Go to **Data & Setup** to select seasons and click Run Data Validation.")
    st.stop()

# Always resolve and pass the run_id explicitly - these are @st.cache_data
# functions cached by argument value, so calling them with no argument
# would keep serving the first run's cached result forever.
readiness_df = field_season_readiness_df(run_id)
detail_df = results_df(run_id)

if not readiness_df.empty:
    covered = sorted(readiness_df["season_id"].unique(), key=lambda s: int(s))
    st.caption("Seasons in this run: " + ", ".join(SEASON_LABELS.get(s, s) for s in covered))

if readiness_df.empty:
    st.stop()

total = len(readiness_df)
ready = int((readiness_df["readiness"] == "READY").sum())
needs_review = int((readiness_df["readiness"] == "NEEDS_REVIEW").sum())
failed = int((readiness_df["readiness"] == "FAILED").sum())

m1, m2, m3, m4 = st.columns(4)
m1.metric("Total field-seasons", f"{total:,}")
m2.metric("READY", f"{ready:,}", f"{ready / total:.0%}")
m3.metric("NEEDS_REVIEW", f"{needs_review:,}", f"{needs_review / total:.0%}")
m4.metric("FAILED", f"{failed:,}", f"{failed / total:.0%}")

st.altair_chart(readiness_status_bar(readiness_df), use_container_width=True)

rules = {r.rule_id: r.name for r in get_rules(validate=False)}
chart_col1, chart_col2, chart_col3 = st.columns(3)

with chart_col1:
    st.subheader("Pass rate per rule")
    applicable = detail_df[detail_df["result"] != "NOT_APPLICABLE"]
    pass_rate = (
        applicable.groupby("rule_id")["result"]
        .apply(lambda s: (s == "PASS").mean())
        .reset_index(name="pass_rate")
    )
    pass_rate["rule_name"] = pass_rate["rule_id"].map(rules)
    st.altair_chart(
        horizontal_magnitude_bar(
            pass_rate, "rule_id", "pass_rate", hue=SEQUENTIAL_BLUE, value_format=".0%", title="Pass rate"
        ),
        use_container_width=True,
    )

with chart_col2:
    st.subheader("What's missing behind NEEDS_REVIEW")
    st.caption(
        "Field-seasons with this data missing (one field-season missing a "
        "diary can drive REVIEW on several rules at once)."
    )
    review_rows = detail_df[detail_df["result"] == "REVIEW"].copy()
    review_rows["missing_list"] = review_rows["missing_inputs"].dropna().map(json.loads)
    exploded = review_rows.explode("missing_list").dropna(subset=["missing_list"])
    exploded["lot_season"] = exploded["lot_id"] + "\x1f" + exploded["season_id"]
    missing_counts = (
        exploded.groupby("missing_list")["lot_season"].nunique().reset_index(name="review_count")
    )
    missing_counts = missing_counts.rename(columns={"missing_list": "missing_input"})
    if missing_counts.empty:
        st.caption("No REVIEW results in this run.")
    else:
        st.altair_chart(
            horizontal_magnitude_bar(
                missing_counts,
                "missing_input",
                "review_count",
                hue=STATUS_WARNING,
                value_format=",d",
                title="Field-seasons missing this",
                category_label="Missing input",
            ),
            use_container_width=True,
        )

with chart_col3:
    st.subheader("Top validation issues")
    issue_counts = (
        detail_df[detail_df["result"] == "FAIL"]
        .groupby("rule_id")
        .size()
        .reset_index(name="fail_count")
    )
    issue_counts["rule_name"] = issue_counts["rule_id"].map(rules)
    if issue_counts.empty:
        st.caption("No FAIL results in this run.")
    else:
        issue_counts = issue_counts.sort_values("rule_id", key=lambda s: s.map(rule_sort_key))
        st.altair_chart(
            horizontal_magnitude_bar(
                issue_counts, "rule_id", "fail_count", hue=STATUS_CRITICAL, value_format=",d", title="Fail count"
            ),
            use_container_width=True,
        )
