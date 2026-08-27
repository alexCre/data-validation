"""Entry point / router. Sets the browser tab title once here (per
Streamlit's rule: st.set_page_config may only be called once, in the file
that calls st.navigation), applies the app-wide font, and explicitly names/
orders the four primary pages - no icons, plain text labels."""

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import streamlit as st

st.set_page_config(page_title="dMRV Data Validation", page_icon="🌾", layout="wide")

# Inter (free, Google Fonts) is set app-wide via .streamlit/config.toml's
# theme.font/headingFont - chosen as a close, license-free match for
# Proxima Nova (see that file's comment to swap in a licensed Proxima Nova
# file later via [[theme.fontFaces]]). The one thing theme options can't
# do is fix Streamlit's own chrome icons:
# without this override they render as literal ligature text (e.g.
# "expand_more") instead of glyphs, because the icon font would otherwise
# inherit theme.font too. Also tightens vertical density - smaller gaps
# between stacked elements and less dead space above the page title - so
# more of the Dashboard/Field Review fits without scrolling.
st.markdown(
    """
    <style>
    [data-testid="stIconMaterial"],
    [data-testid$="Icon"],
    [data-testid*="Icon"],
    .material-symbols-rounded,
    .material-icons {
        font-family: 'Material Symbols Rounded' !important;
    }
    .block-container {
        padding-top: 2rem;
        padding-bottom: 2rem;
    }
    [data-testid="stVerticalBlock"] {
        gap: 0.6rem;
    }
    hr {
        margin: 0.5rem 0;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

pages = {
    "": [
        st.Page("pages/dashboard.py", title="Dashboard"),
        st.Page("pages/field_review.py", title="Field Review"),
    ],
    "Setup": [
        st.Page("pages/data.py", title="Data & Setup", default=True),
        st.Page("pages/rules.py", title="Rules"),
    ],
}

st.navigation(pages).run()
