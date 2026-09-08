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

st.set_page_config(page_title="dMRV Data Validator", page_icon=":material/search:", layout="wide")

# Simple text-password login gate, first thing on every load. The password
# itself doubles as the region selector ("pangasinan" or "cagayan") - each
# grants access to that region's data only (see adapters/csv_adapter.py and
# app/components/state.py's current_region()/get_data_connection()). No
# real auth/identity here, just a shared-secret split by region for this
# PoC, entirely in st.session_state (cleared on browser tab close).
REGION_PASSWORDS = {"pangasinan": "pangasinan", "cagayan": "cagayan"}

if "region" not in st.session_state:
    st.markdown("<div style='height: 12vh'></div>", unsafe_allow_html=True)
    _, center_col, _ = st.columns([1, 1.2, 1])
    with center_col:
        st.markdown("### dMRV Data Validator")
        st.caption("Enter your region password to continue.")
        with st.form("login_form"):
            password = st.text_input("Password", type="password", label_visibility="collapsed", placeholder="Password")
            submitted = st.form_submit_button("Log in", type="primary", use_container_width=True)
        if submitted:
            region = REGION_PASSWORDS.get(password.strip().lower())
            if region is None:
                st.error("Incorrect password.")
            else:
                st.session_state["region"] = region
                st.rerun()
    st.stop()

# App name/wordmark, persistently visible top-left of the sidebar and main
# content area on every page (distinct from page_title above, which only
# affects the browser tab) - a real SVG magnifying-glass icon plus text,
# not an emoji glyph.
st.logo(str(REPO_ROOT / "app" / "assets" / "logo.svg"), size="large")

with st.sidebar:
    st.caption(f"Region: **{st.session_state['region'].title()}**")
    if st.button("Log out", use_container_width=True):
        del st.session_state["region"]
        st.rerun()

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
