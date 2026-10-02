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
    STATUS_GOOD,
    STATUS_WARNING,
)
from app.components.copilot_ui import render_copilot_launcher
from app.components.ui import card, chip, empty_state, kpi_row, page_header, section
from app.components.state import field_season_readiness_df, get_rules, results_df

render_copilot_launcher()

SEASON_LABELS = season_labels()  # {"3": "Dry Crop 2025", "4": "Wet Crop 2025"}

# Session-scoped, not the persisted store's latest run - the app should
# start empty (no Dashboard/Field Review content) until Run Data Validation
# is clicked on the Data & Setup page in this session, even if a prior run
# exists on disk.
run_id = st.session_state.get("validation_run_id")
if run_id is None:
    page_header("Dashboard", "Readiness of every field-season, and the rules driving it.", eyebrow="Results")
    empty_state(
        "No validation run yet",
        "Go to <b>Data &amp; Setup</b>, select a season and click <b>Run Data Validation</b>.",
    )
    st.stop()

# Always resolve and pass the run_id explicitly - these are @st.cache_data
# functions cached by argument value, so calling them with no argument
# would keep serving the first run's cached result forever.
readiness_df = field_season_readiness_df(run_id)
detail_df = results_df(run_id)

_chips = []
if not readiness_df.empty:
    covered = sorted(readiness_df["season_id"].unique(), key=lambda s: int(s))
    _chips = [chip(SEASON_LABELS.get(s, s), "brand") for s in covered] + [chip(f"Run {run_id}")]
page_header(
    "Dashboard",
    "Readiness of every field-season, and the rules driving it.",
    eyebrow="Results",
    chips=_chips,
)

if readiness_df.empty:
    st.stop()

total = len(readiness_df)
ready = int((readiness_df["readiness"] == "READY").sum())
needs_review = int((readiness_df["readiness"] == "NEEDS_REVIEW").sum())
failed = int((readiness_df["readiness"] == "FAILED").sum())

kpi_row(
    [
        {"label": "Total field-seasons", "value": f"{total:,}", "sub": "in this run", "accent": "#2a78d6"},
        {"label": "Ready", "value": f"{ready:,}", "sub": f"{ready / total:.0%} of total", "accent": STATUS_GOOD},
        {"label": "Needs review", "value": f"{needs_review:,}", "sub": f"{needs_review / total:.0%} of total", "accent": "#d99200"},
        {"label": "Failed", "value": f"{failed:,}", "sub": f"{failed / total:.0%} of total", "accent": STATUS_CRITICAL},
    ]
)

with card("readiness"):
    section("Readiness breakdown")
    st.altair_chart(readiness_status_bar(readiness_df), use_container_width=True)

rules = {r.rule_id: r.name for r in get_rules(validate=False)}
CHART_HEIGHT = max(len(rules), 1) * 28  # same plot height in all three cards so they line up
chart_col1, chart_col2, chart_col3 = st.columns(3)

with chart_col1, card("passrate"):
    section("Pass rate per rule", "Share of applicable field-seasons that passed.")
    applicable = detail_df[detail_df["result"] != "NOT_APPLICABLE"]
    pass_rate = (
        applicable.groupby("rule_id")["result"]
        .apply(lambda s: (s == "PASS").mean())
        .reset_index(name="pass_rate")
    )
    pass_rate["rule_name"] = pass_rate["rule_id"].map(rules)
    st.altair_chart(
        horizontal_magnitude_bar(
            pass_rate,
            "rule_id",
            "pass_rate",
            hue=SEQUENTIAL_BLUE,
            value_format=".0%",
            title="Pass rate",
            domain_max=1.0,
            show_track=True,
            name_col="rule_name",
            height=CHART_HEIGHT,
        ),
        use_container_width=True,
    )

with chart_col2, card("missing"):
    section(
        "Missing data behind review",
        "Field-seasons missing each input.",
        hint="One gap can drive REVIEW on several rules, so counts overlap.",
    )
    review_rows = detail_df[detail_df["result"] == "REVIEW"].copy()
    review_rows["missing_list"] = review_rows["missing_inputs"].dropna().map(json.loads)
    exploded = review_rows.explode("missing_list").dropna(subset=["missing_list"])
    exploded["lot_season"] = exploded["lot_id"] + "\x1f" + exploded["season_id"]
    missing_counts = (
        exploded.groupby("missing_list")["lot_season"].nunique().reset_index(name="review_count")
    )
    missing_counts = missing_counts.rename(columns={"missing_list": "source_column"})
    # Short, readable axis labels ("straw management date"); the full
    # table.column id stays in the tooltip.
    missing_counts["missing_input"] = (
        missing_counts["source_column"].str.split(".").str[-1].str.replace("_", " ", regex=False)
    )
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
                name_col="source_column",
                name_title="Source column",
                sort_by_value=True,
                height=CHART_HEIGHT,
            ),
            use_container_width=True,
        )

with chart_col3, card("issues"):
    section("Top validation issues", "Field-seasons failing each rule.")
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
                issue_counts,
                "rule_id",
                "fail_count",
                hue=STATUS_CRITICAL,
                value_format=",d",
                title="Fail count",
                name_col="rule_name",
                height=CHART_HEIGHT,
            ),
            use_container_width=True,
        )
