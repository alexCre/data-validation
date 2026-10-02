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

from app.components.ui import card, chip, hide_sidebar, inject_global_css

st.set_page_config(page_title="dMRV Data Validator", page_icon=":material/search:", layout="wide")

# Simple text-password login gate, first thing on every load. The password
# itself doubles as the region selector ("pangasinan" or "cagayan") - each
# grants access to that region's data only (see adapters/csv_adapter.py and
# app/components/state.py's current_region()/get_data_connection()). No
# real auth/identity here, just a shared-secret split by region for this
# PoC, entirely in st.session_state (cleared on browser tab close).
REGION_PASSWORDS = {"pangasinan": "pangasinan", "cagayan": "cagayan"}

if "region" not in st.session_state:
    inject_global_css()
    hide_sidebar()
    st.markdown("<div style='height: 9vh'></div>", unsafe_allow_html=True)
    _, center_col, _ = st.columns([1, 1.15, 1])
    with center_col:
        st.markdown(
            """
            <div class="login-wrap">
              <div class="login-logo">&#10003;</div>
              <div class="login-title">dMRV Data Validator</div>
              <div class="login-sub">Agentic, auditable validation of monitoring data.<br/>Enter your region password to continue.</div>
            </div>
            """,
            unsafe_allow_html=True,
        )
        with card("login"):
            with st.form("login_form", border=False):
                password = st.text_input("Password", type="password", label_visibility="collapsed", placeholder="Region password")
                submitted = st.form_submit_button("Log in", type="primary", use_container_width=True)
            if submitted:
                region = REGION_PASSWORDS.get(password.strip().lower())
                if region is None:
                    st.error("Incorrect password.")
                else:
                    st.session_state["region"] = region
                    st.rerun()
        st.markdown(
            "<div style='text-align:center;color:#94a3b8;font-size:.82rem;margin-top:.4rem'>"
            "Deterministic C1-C9 rules · no LLM decides a validation outcome</div>",
            unsafe_allow_html=True,
        )
    st.stop()

# App name/wordmark, persistently visible top-left of the sidebar and main
# content area on every page (distinct from page_title above, which only
# affects the browser tab) - a real SVG magnifying-glass icon plus text,
# not an emoji glyph.
st.logo(str(REPO_ROOT / "app" / "assets" / "logo.svg"), size="large")

with st.sidebar:
    st.markdown(
        "<div style='margin:.2rem 0 .4rem 0'><span style='font-size:.7rem;font-weight:700;letter-spacing:.08em;"
        "text-transform:uppercase;color:#64748b'>Region</span><br/>"
        + chip(st.session_state["region"].title(), "brand", dot=True)
        + "</div>",
        unsafe_allow_html=True,
    )
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
inject_global_css()

pages = {
    "Validate": [
        st.Page("pages/data.py", title="Data & Setup", icon=":material/database:", default=True),
        st.Page("pages/dashboard.py", title="Dashboard", icon=":material/monitoring:"),
        st.Page("pages/field_review.py", title="Field Review", icon=":material/fact_check:"),
    ],
    "Configure": [
        st.Page("pages/rules.py", title="Rules", icon=":material/rule:"),
    ],
}

st.navigation(pages).run()
