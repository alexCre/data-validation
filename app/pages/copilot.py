"""Validation Copilot - an additional, on-demand conversational layer over
the existing deterministic validation system. Never replaces Dashboard/
Data & Setup/Rules/Field Review, and never decides a validation outcome or
activates a rule itself (see agents/validation_copilot.py). This is the
full-screen surface (Option A); render_copilot_launcher() embeds the same
chat as a popup dialog on the other pages (Option B) - see
app/components/copilot_ui.py, which both share.
"""

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import streamlit as st

from app.components.copilot_ui import render_copilot_chat

st.title("Copilot")
st.caption(
    "Conversational access to validation results and supported actions - an additional "
    "layer on top of Dashboard / Data & Setup / Rules / Field Review, not a replacement."
)

render_copilot_chat()
