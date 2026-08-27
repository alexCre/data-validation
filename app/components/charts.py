"""Altair chart builders, following the dataviz skill's method: form picked
by the data's job, color computed (status palette for pass/fail state,
single sequential hue for magnitude), thin rounded bars, hover tooltips,
legend for multi-series. Palette values are the validated defaults from the
skill's reference palette (references/palette.md).
"""

from __future__ import annotations

import re

import altair as alt
import pandas as pd
import streamlit as st

STATUS_GOOD = "#0ca30c"
STATUS_WARNING = "#fab219"
STATUS_CRITICAL = "#d03b3b"
SEQUENTIAL_BLUE = "#2a78d6"

READINESS_ORDER = ["READY", "NEEDS_REVIEW", "FAILED"]
READINESS_COLORS = {"READY": STATUS_GOOD, "NEEDS_REVIEW": STATUS_WARNING, "FAILED": STATUS_CRITICAL}


def _theme_ink() -> dict[str, str]:
    """Text/grid colors that read on both Streamlit theme modes - charts
    otherwise use a transparent background and inherit the page surface."""
    base = st.get_option("theme.base") or "light"
    if base == "dark":
        return {"ink": "#ffffff", "muted": "#c3c2b7", "grid": "#2c2c2a"}
    return {"ink": "#0b0b0b", "muted": "#52514e", "grid": "#e1e0d9"}


def _configure(chart: alt.Chart) -> alt.Chart:
    ink = _theme_ink()
    return (
        chart.configure(background="transparent", font="Inter, -apple-system, Helvetica Neue, Arial, sans-serif")
        .configure_axis(
            labelColor=ink["muted"],
            titleColor=ink["muted"],
            gridColor=ink["grid"],
            domainColor=ink["grid"],
            tickColor=ink["grid"],
        )
        .configure_legend(labelColor=ink["ink"], titleColor=ink["ink"])
        .configure_view(strokeWidth=0)
        .configure_text(color=ink["ink"])
    )


def rule_sort_key(rule_id: str) -> tuple[int, str]:
    """Natural sort for rule ids (C1, C2, ..., C10, C11), not lexical (which
    would put C10/C11 between C1 and C2). Non-C-prefixed custom rule ids
    sort after, alphabetically."""
    match = re.fullmatch(r"C(\d+)", rule_id)
    if match:
        return (0, f"{int(match.group(1)):04d}")
    return (1, rule_id)


def readiness_status_bar(readiness_df: pd.DataFrame) -> alt.Chart:
    """Part-to-whole: a single 100%-stacked horizontal bar of
    READY/NEEDS_REVIEW/FAILED - a status/state breakdown, so it wears the
    fixed status palette, not a categorical one."""
    counts = (
        readiness_df["readiness"].value_counts().reindex(READINESS_ORDER, fill_value=0).rename_axis("readiness").reset_index(name="count")
    )
    total = int(counts["count"].sum())
    counts["share"] = counts["count"] / total if total else 0.0
    counts["rank"] = counts["readiness"].map({v: i for i, v in enumerate(READINESS_ORDER)})
    counts["row"] = "Field-seasons"

    chart = (
        alt.Chart(counts)
        .mark_bar(height=24, cornerRadiusEnd=4)
        .encode(
            x=alt.X("count:Q", stack="normalize", axis=None),
            y=alt.Y("row:N", axis=None, title=None),
            order=alt.Order("rank:Q"),
            color=alt.Color(
                "readiness:N",
                scale=alt.Scale(domain=READINESS_ORDER, range=[READINESS_COLORS[k] for k in READINESS_ORDER]),
                legend=alt.Legend(title=None, orient="bottom"),
            ),
            tooltip=[
                alt.Tooltip("readiness:N", title="Status"),
                alt.Tooltip("count:Q", title="Field-seasons", format=",d"),
                alt.Tooltip("share:Q", title="Share", format=".0%"),
            ],
        )
        .properties(height=48)
    )
    return _configure(chart)


def horizontal_magnitude_bar(
    df: pd.DataFrame,
    category_col: str,
    value_col: str,
    *,
    hue: str,
    value_format: str,
    title: str | None = None,
    category_label: str = "Rule",
) -> alt.Chart:
    """A single-hue horizontal bar comparing magnitude across nominal
    categories (rule ids) - sequential-style single hue, not one color per
    bar, since the bars aren't distinct identities to tell apart. Value
    labelled at the bar tip (every bar, not just extremes - there are only
    ever up to ~12 rules, and exact reading matters for a validation
    dashboard)."""
    df = df.copy()
    order = sorted(df[category_col].tolist(), key=rule_sort_key)

    base = alt.Chart(df).encode(
        y=alt.Y(f"{category_col}:N", sort=order, title=None, axis=alt.Axis(labelLimit=0)),
        x=alt.X(f"{value_col}:Q", axis=alt.Axis(format=value_format), title=title),
    )
    bars = base.mark_bar(height=16, cornerRadiusEnd=4, color=hue).encode(
        tooltip=[
            alt.Tooltip(f"{category_col}:N", title=category_label),
            alt.Tooltip(f"{value_col}:Q", title=title or value_col, format=value_format),
        ]
    )
    labels = base.mark_text(align="left", dx=4, color=_theme_ink()["ink"]).encode(
        text=alt.Text(f"{value_col}:Q", format=value_format)
    )
    return _configure((bars + labels).properties(height=alt.Step(22)))


def geometry_coverage_chart(coverage_df: pd.DataFrame) -> alt.Chart:
    """Per-season has-geometry vs missing-geometry - a binary that means
    good/bad (a lot data-quality signal, not itself a validation rule), so
    it wears status good/critical, not a categorical hue."""
    df = coverage_df.copy()
    df["missing_geometry"] = df["field_seasons"] - df["has_geometry"]
    long_df = df.melt(
        id_vars=["season_id"],
        value_vars=["has_geometry", "missing_geometry"],
        var_name="status",
        value_name="count",
    )
    status_labels = {"has_geometry": "Has geometry", "missing_geometry": "Missing geometry"}
    long_df["status_label"] = long_df["status"].map(status_labels)
    order = ["Has geometry", "Missing geometry"]
    colors = {"Has geometry": STATUS_GOOD, "Missing geometry": STATUS_CRITICAL}
    long_df["rank"] = long_df["status_label"].map({v: i for i, v in enumerate(order)})

    chart = (
        alt.Chart(long_df)
        .mark_bar(height=20, cornerRadiusEnd=4)
        .encode(
            y=alt.Y("season_id:N", title="Season"),
            x=alt.X("count:Q", title="Field-seasons", axis=alt.Axis(format=",d")),
            order=alt.Order("rank:Q"),
            color=alt.Color(
                "status_label:N",
                scale=alt.Scale(domain=order, range=[colors[k] for k in order]),
                legend=alt.Legend(title=None, orient="bottom"),
            ),
            tooltip=[
                alt.Tooltip("season_id:N", title="Season"),
                alt.Tooltip("status_label:N", title="Status"),
                alt.Tooltip("count:Q", title="Field-seasons", format=",d"),
            ],
        )
        .properties(height=alt.Step(28))
    )
    return _configure(chart)
