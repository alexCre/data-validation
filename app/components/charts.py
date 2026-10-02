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


READINESS_LABELS = {"READY": "Ready", "NEEDS_REVIEW": "Needs review", "FAILED": "Failed"}
# Text on a status fill: white on green/red, dark on amber (contrast).
READINESS_TEXT = {"READY": "#ffffff", "NEEDS_REVIEW": "#3b2a00", "FAILED": "#ffffff"}
TRACK = "#eef2f7"


def readiness_status_bar(readiness_df: pd.DataFrame) -> alt.Chart:
    """Part-to-whole: a single 100%-stacked horizontal bar of
    READY/NEEDS_REVIEW/FAILED (status palette, not categorical). Segments
    are laid out explicitly (start/end share) so each can carry a direct
    label - share and count - centered inside it, with a 2px surface gap
    between fills. Segments too narrow for a label stay unlabeled; the
    legend and tooltip still identify them."""
    counts = (
        readiness_df["readiness"].value_counts().reindex(READINESS_ORDER, fill_value=0).rename_axis("readiness").reset_index(name="count")
    )
    total = int(counts["count"].sum())
    counts["share"] = counts["count"] / total if total else 0.0
    counts["end"] = counts["share"].cumsum()
    counts["start"] = counts["end"] - counts["share"]
    counts["mid"] = (counts["start"] + counts["end"]) / 2
    counts["status"] = counts["readiness"].map(READINESS_LABELS)
    counts["label"] = counts.apply(
        lambda r: f"{r['status']}  {r['share']:.0%}" if r["share"] >= 0.14 else (f"{r['share']:.0%}" if r["share"] >= 0.05 else ""),
        axis=1,
    )
    counts["text_color"] = counts["readiness"].map(READINESS_TEXT)
    counts["row"] = "Field-seasons"
    status_order = [READINESS_LABELS[k] for k in READINESS_ORDER]
    color = alt.Color(
        "status:N",
        scale=alt.Scale(domain=status_order, range=[READINESS_COLORS[k] for k in READINESS_ORDER]),
        legend=alt.Legend(title=None, orient="bottom", symbolType="square", labelFontSize=12, padding=4),
    )
    x_scale = alt.Scale(domain=[0, 1], nice=False)
    tooltip = [
        alt.Tooltip("status:N", title="Status"),
        alt.Tooltip("count:Q", title="Field-seasons", format=",d"),
        alt.Tooltip("share:Q", title="Share", format=".1%"),
    ]
    bars = (
        alt.Chart(counts)
        .mark_bar(size=34, cornerRadius=6, stroke="#ffffff", strokeWidth=2)
        .encode(
            x=alt.X("start:Q", axis=None, scale=x_scale),
            x2="end:Q",
            y=alt.Y("row:N", axis=None, title=None),
            color=color,
            tooltip=tooltip,
        )
    )
    labels = (
        alt.Chart(counts[counts["label"] != ""])
        .mark_text(fontSize=13, fontWeight=600)
        .encode(
            x=alt.X("mid:Q", axis=None, scale=x_scale),
            y=alt.Y("row:N", axis=None, title=None),
            text="label:N",
            color=alt.Color("text_color:N", scale=None),
        )
    )
    return _configure((bars + labels).properties(height=64))


def horizontal_magnitude_bar(
    df: pd.DataFrame,
    category_col: str,
    value_col: str,
    *,
    hue: str,
    value_format: str,
    title: str | None = None,
    category_label: str = "Rule",
    domain_max: float | None = None,
    show_track: bool = False,
    height: int | None = None,
    name_col: str | None = None,
    name_title: str = "Name",
    sort_by_value: bool = False,
) -> alt.Chart:
    """Single-hue horizontal bars comparing magnitude across nominal
    categories (rule ids). Every bar is labelled at its tip, so the value
    axis is dropped entirely (direct labels beat a ruler here) and the chart
    reads as bars + numbers, nothing else. `domain_max` pins the scale (1.0
    for percentages, plus label headroom); `show_track` draws a faint
    full-width track behind each bar so a 100% bar still reads as 'full'.
    A fixed `height` keeps side-by-side cards the same size no matter how
    many categories each has. `name_col` (e.g. rule name) is tooltip-only."""
    df = df.copy()
    if sort_by_value:
        order = df.sort_values(value_col, ascending=False)[category_col].tolist()
    else:
        order = sorted(df[category_col].tolist(), key=rule_sort_key)
    if height is None:
        height = max(len(df), 1) * 28
    max_value = float(df[value_col].max()) if len(df) else 1.0
    track_end = domain_max if domain_max is not None else max_value
    df["_track"] = track_end
    scale = alt.Scale(domain=[0, track_end * (1.18 if (show_track or domain_max) else 1.12)], nice=False)

    y = alt.Y(
        f"{category_col}:N",
        sort=order,
        title=None,
        axis=alt.Axis(labelLimit=170, labelFontSize=12, labelPadding=10, ticks=False, domain=False),
        scale=alt.Scale(paddingInner=0.35, paddingOuter=0.1),
    )
    tooltip = [alt.Tooltip(f"{category_col}:N", title=category_label)]
    if name_col and name_col in df.columns:
        tooltip.append(alt.Tooltip(f"{name_col}:N", title=name_title))
    tooltip.append(alt.Tooltip(f"{value_col}:Q", title=title or value_col, format=value_format))

    layers = []
    if show_track:
        layers.append(
            alt.Chart(df).mark_bar(color=TRACK, cornerRadiusEnd=5, size=16).encode(
                y=y, x=alt.X("_track:Q", axis=None, scale=scale)
            )
        )
    layers.append(
        alt.Chart(df)
        .mark_bar(color=hue, cornerRadiusEnd=5, size=16)
        .encode(y=y, x=alt.X(f"{value_col}:Q", axis=None, scale=scale), tooltip=tooltip)
    )
    layers.append(
        alt.Chart(df)
        .mark_text(align="left", dx=7, fontSize=12, fontWeight=600, color=_theme_ink()["ink"])
        .encode(y=y, x=alt.X(f"{value_col}:Q", axis=None, scale=scale), text=alt.Text(f"{value_col}:Q", format=value_format))
    )
    # Right padding keeps the longest bar's value label inside the canvas.
    return _configure(
        alt.layer(*layers).properties(
            height=height,
            padding={"left": 2, "right": 36, "top": 4, "bottom": 4},
            autosize=alt.AutoSizeParams(type="fit", contains="padding"),
        )
    )


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
            y=alt.Y("season_id:N", title=None, axis=alt.Axis(labelFontSize=12, ticks=False, domain=False)),
            x=alt.X("count:Q", title=None, axis=alt.Axis(format=",d", labelFontSize=11)),
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
