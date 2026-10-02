"""Shared look-and-feel for the Streamlit app: one global stylesheet plus a
few small presentation helpers (page header, KPI cards, status pills,
section titles, empty states). Presentation only - no validation logic.

Design tokens are CSS variables on :root so every page/component pulls from
one place. The app is light-themed (see .streamlit/config.toml)."""

from __future__ import annotations

import html

import streamlit as st

_card_counter = {"n": 0}

BRAND = "#2a78d6"
GOOD = "#0ca30c"
WARN = "#fab219"
BAD = "#d03b3b"

_GLOBAL_CSS = """
<style>
:root {
  --bg: #f5f7fa;
  --card: #ffffff;
  --border: #e4e8ee;
  --ink: #0f172a;
  --muted: #64748b;
  --brand: #2a78d6;
  --brand-soft: #eaf2fc;
  --good: #0ca30c;  --good-soft: #e7f6e7;
  --warn: #b97a00;  --warn-soft: #fff4d6;
  --bad: #d03b3b;   --bad-soft: #fbeaea;
  --shadow: 0 1px 2px rgba(15,23,42,.04), 0 4px 14px rgba(15,23,42,.05);
  --radius: 14px;
}

/* ---- Icon font safety (Streamlit chrome icons) ---- */
[data-testid="stIconMaterial"], [data-testid$="Icon"], [data-testid*="Icon"],
.material-symbols-rounded, .material-icons {
  font-family: 'Material Symbols Rounded' !important;
}

/* ---- Canvas ---- */
.stApp { background: var(--bg); }
[data-testid="stHeader"] { background: transparent; }
[data-testid="stDeployButton"], [data-testid="stAppDeployButton"], .stAppDeployButton, [data-testid="stMainMenu"], #MainMenu, footer { display: none !important; }
.block-container { padding-top: 2.2rem; padding-bottom: 3rem; max-width: 1280px; }
[data-testid="stVerticalBlock"] { gap: 0.9rem; }
hr { margin: 1rem 0; border-color: var(--border); }

/* ---- Typography ---- */
.kpi .k-value, [data-testid="stMetricValue"], [data-testid="stDataFrame"] {
  font-variant-numeric: tabular-nums;
}
.pg-title, .sec-title, .login-title { text-wrap: balance; }
code, [data-testid="stCaptionContainer"] code, .stMarkdown code {
  font-size: .82em; padding: .1em .4em; border-radius: 6px; font-weight: 500;
}
h1, h2, h3, h4 { color: var(--ink); letter-spacing: -0.01em; }
h2, h3 { margin-top: .4rem; }
[data-testid="stCaptionContainer"], .stCaption { color: var(--muted); }

/* ---- Sidebar ---- */
[data-testid="stSidebar"] {
  background: #ffffff;
  border-right: 1px solid var(--border);
}
[data-testid="stSidebarNav"] a, [data-testid="stSidebarNavLink"] {
  border-radius: 10px; margin: 2px 6px; padding: .45rem .7rem; font-weight: 500;
}
[data-testid="stSidebarNavLink"][aria-current="page"] {
  background: var(--brand-soft); color: var(--brand); font-weight: 600;
}
[data-testid="stSidebarNavLink"]:hover { background: #f1f5f9; }
[data-testid="stSidebarNav"] span[data-testid="stHeaderGroupTitle"],
[data-testid="stSidebarNavSeparator"] { color: var(--muted); }

/* ---- Cards: bordered containers ---- */
/* st.container(border=True) is tagged via border rule below; the helper
   card() in ui.py gives a keyed container so we can target it safely. */
[class*="st-key-card"] {
  background: var(--card); border: 1px solid var(--border) !important;
  border-radius: var(--radius) !important; box-shadow: var(--shadow); padding: 1.15rem 1.5rem;
}

/* metrics nested inside a card go flat (no double borders) */
[class*="st-key-card"] [data-testid="stMetric"] { border: 0; box-shadow: none; padding: .2rem 0; background: transparent; }
/* no frame-in-frame: expanders inside a card become a plain divider row */
[class*="st-key-card"] [data-testid="stExpander"] {
  background: transparent; border: 0 !important; border-top: 1px solid var(--border) !important;
  border-radius: 0; margin-top: .3rem;
}
[class*="st-key-card"] [data-testid="stExpander"] details { border: 0 !important; background: transparent; box-shadow: none; }

/* ---- Native metrics -> card look ---- */
[data-testid="stMetric"] {
  background: var(--card); border: 1px solid var(--border);
  border-radius: var(--radius); padding: .9rem 1.1rem; box-shadow: var(--shadow);
}
[data-testid="stMetricLabel"] p { color: var(--muted); font-weight: 500; font-size: .8rem; }
[data-testid="stMetricValue"] { color: var(--ink); }

/* ---- Buttons ---- */
.stButton > button, .stDownloadButton > button {
  border-radius: 10px; font-weight: 600; border: 1px solid var(--border);
  padding: .5rem 1rem; transition: box-shadow .15s, transform .05s, background .15s;
}
.stButton > button:hover, .stDownloadButton > button:hover {
  border-color: var(--brand); color: var(--brand); box-shadow: 0 2px 8px rgba(42,120,214,.15);
}
.stButton > button[kind="primary"], .stDownloadButton > button[kind="primary"] {
  background: linear-gradient(180deg, #3585e6, #2a78d6); color: #fff; border: 0;
  box-shadow: 0 2px 6px rgba(42,120,214,.35);
}
.stButton > button[kind="primary"]:hover, .stDownloadButton > button[kind="primary"]:hover {
  color: #fff; box-shadow: 0 4px 12px rgba(42,120,214,.45);
}

/* ---- Inputs ---- */
[data-baseweb="input"], [data-baseweb="select"] > div, [data-baseweb="textarea"] {
  border-radius: 10px !important; background: #fff;
}

/* ---- Tables ---- */
[data-testid="stDataFrame"] {
  border: 1px solid var(--border); border-radius: var(--radius);
  overflow: hidden; box-shadow: var(--shadow);
}

/* ---- Expanders ---- */
[data-testid="stExpander"] {
  background: var(--card); border: 1px solid var(--border) !important;
  border-radius: 12px; box-shadow: none;
}
[data-testid="stExpander"] summary { font-weight: 600; }

/* ---- Alerts ---- */
[data-testid="stAlert"] { border-radius: 12px; border: 1px solid var(--border); }

/* ---- Charts sit on a card ---- */
[data-testid="stArrowVegaLiteChart"], [data-testid="stVegaLiteChart"] {
  background: transparent;
}

/* ================= Custom components ================= */
.pg-head { margin: 0 0 1.1rem 0; }
.pg-eyebrow {
  font-size: .72rem; font-weight: 700; letter-spacing: .09em; text-transform: uppercase;
  color: var(--brand); margin-bottom: .25rem;
}
.pg-title { font-size: 1.85rem; font-weight: 700; color: var(--ink); line-height: 1.15; margin: 0; }
.pg-sub { color: var(--muted); font-size: .95rem; margin-top: .35rem; max-width: 95ch; text-wrap: pretty; }
.pg-chips { margin-top: .6rem; display: flex; gap: .4rem; flex-wrap: wrap; }

.sec-title { font-size: 1.05rem; font-weight: 650; color: var(--ink); margin: .6rem 0 0 0; }
.sec-cap { color: var(--muted); font-size: .85rem; margin: .1rem 0 .4rem 0; }

.chip {
  display: inline-flex; align-items: center; gap: .35rem; font-size: .75rem; font-weight: 600;
  padding: .2rem .6rem; border-radius: 999px; background: #eef1f5; color: #334155;
  border: 1px solid var(--border);
}
.chip.good { background: var(--good-soft); color: #0a7a0a; border-color: #cdebcd; }
.chip.warn { background: var(--warn-soft); color: var(--warn); border-color: #f5e0a3; }
.chip.bad  { background: var(--bad-soft);  color: var(--bad);  border-color: #f2c9c9; }
.chip.brand{ background: var(--brand-soft); color: var(--brand); border-color: #cfe1f7; }
.chip .dot { width: 7px; height: 7px; border-radius: 50%; background: currentColor; }

.kpi-grid { margin-bottom: .9rem; display: grid; grid-template-columns: repeat(4, minmax(0,1fr)); gap: .9rem; }
@media (max-width: 900px) { .kpi-grid { grid-template-columns: repeat(2, minmax(0,1fr)); } }
.kpi {
  background: var(--card); border: 1px solid var(--border); border-radius: var(--radius);
  padding: 1.1rem 1.4rem; box-shadow: var(--shadow);
}
.kpi .k-label::before {
  content: ""; display: inline-block; width: 8px; height: 8px; border-radius: 50%;
  background: var(--accent, var(--brand)); margin-right: .55rem; vertical-align: 1px;
}
.kpi .k-label { color: var(--muted); font-size: .78rem; font-weight: 600; letter-spacing: .02em; text-transform: uppercase; }
.kpi .k-value { color: var(--ink); font-size: 1.9rem; font-weight: 700; line-height: 1.2; margin-top: .2rem; }
.kpi .k-sub { margin-top: .15rem; font-size: .82rem; font-weight: 600; color: var(--accent, var(--muted)); }

.src { display: flex; flex-direction: column; margin: .1rem 0 .55rem 0; min-width: 0; }
.src-l { font-size: .78rem; font-weight: 600; color: var(--muted); }
.src-f { font-size: .68rem; line-height: 1.35; color: #334155; white-space: normal; overflow-wrap: anywhere;
  font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; }

.empty {
  background: var(--card); border: 1px dashed #cbd5e1; border-radius: var(--radius);
  padding: 2.2rem 1.5rem; text-align: center;
}
.empty .e-title { font-weight: 650; color: var(--ink); font-size: 1.05rem; }
.empty .e-body { color: var(--muted); margin-top: .3rem; }

/* ---- Login ---- */
.login-wrap { text-align: center; margin-bottom: .6rem; }
.login-logo {
  width: 54px; height: 54px; margin: 0 auto .8rem auto; border-radius: 16px;
  background: linear-gradient(135deg, #3b8ae8, #1f5fb0); color: #fff; display: flex;
  align-items: center; justify-content: center; font-size: 1.6rem;
  box-shadow: 0 8px 20px rgba(42,120,214,.35);
}
.login-title { font-size: 1.5rem; font-weight: 700; color: var(--ink); }
.login-sub { color: var(--muted); margin-top: .25rem; font-size: .92rem; }
</style>
"""


def hide_sidebar() -> None:
    """For the pre-login screen: no nav, no sidebar toggle."""
    st.markdown(
        "<style>[data-testid='stSidebar'],[data-testid='stSidebarCollapsedControl'],"
        "[data-testid='stSidebarNav']{display:none !important}</style>",
        unsafe_allow_html=True,
    )


def inject_global_css() -> None:
    _card_counter["n"] = 0  # entry script runs first on every rerun -> stable card keys
    st.markdown(_GLOBAL_CSS, unsafe_allow_html=True)


def _e(text: object) -> str:
    return html.escape(str(text))


def chip(text: str, tone: str = "", dot: bool = False) -> str:
    """Return HTML for a small pill. tone: good | warn | bad | brand | ''."""
    dot_html = '<span class="dot"></span>' if dot else ""
    return f'<span class="chip {tone}">{dot_html}{_e(text)}</span>'


def readiness_chip(status: str) -> str:
    tone = {"READY": "good", "NEEDS_REVIEW": "warn", "FAILED": "bad"}.get(status, "")
    return chip(status.replace("_", " ").title() if status != "READY" else "Ready", tone, dot=True)


def page_header(title: str, subtitle: str = "", eyebrow: str = "", chips: list[str] | None = None) -> None:
    """Title block used at the top of every page. `chips` are pre-rendered
    HTML from chip()."""
    parts = ['<div class="pg-head">']
    if eyebrow:
        parts.append(f'<div class="pg-eyebrow">{_e(eyebrow)}</div>')
    parts.append(f'<div class="pg-title">{_e(title)}</div>')
    if subtitle:
        parts.append(f'<div class="pg-sub">{subtitle}</div>')
    if chips:
        parts.append('<div class="pg-chips">' + "".join(chips) + "</div>")
    parts.append("</div>")
    st.markdown("".join(parts), unsafe_allow_html=True)


def section(title: str, caption: str = "", hint: str = "") -> None:
    """Section heading + one-line caption. `hint` is longer fine print shown
    as a hover tooltip on the caption (keeps the caption to one line)."""
    st.markdown(f'<div class="sec-title">{_e(title)}</div>', unsafe_allow_html=True)
    if caption:
        tip = f' title="{_e(hint)}"' if hint else ""
        st.markdown(f'<div class="sec-cap"{tip}>{_e(caption)}</div>', unsafe_allow_html=True)


def kpi_row(items: list[dict]) -> None:
    """items: [{label, value, sub?, accent?}] - accent is a hex color."""
    cards = []
    for it in items:
        accent = it.get("accent", BRAND)
        sub = f'<div class="k-sub">{_e(it["sub"])}</div>' if it.get("sub") else ""
        cards.append(
            f'<div class="kpi" style="--accent:{accent}">'
            f'<div class="k-label">{_e(it["label"])}</div>'
            f'<div class="k-value">{_e(it["value"])}</div>{sub}</div>'
        )
    st.markdown('<div class="kpi-grid">' + "".join(cards) + "</div>", unsafe_allow_html=True)


def empty_state(title: str, body: str) -> None:
    st.markdown(
        f'<div class="empty"><div class="e-title">{_e(title)}</div><div class="e-body">{body}</div></div>',
        unsafe_allow_html=True,
    )



def card(key: str | None = None):
    """A white elevated card container: `with card(): ...`. Uses a keyed
    st.container so the global CSS ([class*='st-key-card']) can style it."""
    if key is None:
        _card_counter["n"] += 1
        key = f"auto{_card_counter['n']}"
    return st.container(key=f"card_{key}")
