"""Streamlit session-state helpers for the Copilot page: bounded
conversation history (no long-term/cross-user memory - see spec section 8)
and the Developer Mode tool-call trace. Session-local only."""

from __future__ import annotations

import uuid
from datetime import datetime

import streamlit as st

from app.components.state import get_store_connection
from persistence import duckdb_store

# Caps how many prior text turns are replayed to the model each request -
# bounds context growth across a long session without needing summarization.
MAX_HISTORY_MESSAGES = 20


def get_session_id() -> str:
    if "copilot_session_id" not in st.session_state:
        st.session_state["copilot_session_id"] = uuid.uuid4().hex[:16]
    return st.session_state["copilot_session_id"]


def get_chat_history() -> list[dict]:
    """The plain user/assistant text history fed to ValidationCopilot.run()
    for conversational context - deliberately NOT the raw tool_use/
    tool_result exchange from each turn (that stays internal to a single
    .run() call), so this never accumulates orphaned tool blocks."""
    return st.session_state.setdefault("copilot_chat_history", [])


def append_chat_history(role: str, text: str) -> None:
    history = get_chat_history()
    history.append({"role": role, "content": text})
    if len(history) > MAX_HISTORY_MESSAGES:
        del history[: len(history) - MAX_HISTORY_MESSAGES]


def get_display_turns() -> list[dict]:
    """Richer per-turn records for rendering the chat UI: text plus the
    tool-call trace and any structured attachment (export file, rule
    preview) the page can turn into buttons/tables."""
    return st.session_state.setdefault("copilot_display_turns", [])


def append_display_turn(role: str, text: str, tool_calls: list | None = None, attachment: dict | None = None) -> None:
    get_display_turns().append({"role": role, "text": text, "tool_calls": tool_calls or [], "attachment": attachment})


def next_turn_number() -> int:
    st.session_state["copilot_turn_counter"] = st.session_state.get("copilot_turn_counter", 0) + 1
    return st.session_state["copilot_turn_counter"]


def reset_conversation() -> None:
    st.session_state["copilot_chat_history"] = []
    st.session_state["copilot_display_turns"] = []
    st.session_state["copilot_turn_counter"] = 0


def log_tool_calls(turn: int, tool_calls: list) -> None:
    """Persists each tool call for this turn (audit trail / Developer Mode
    history across reruns) - never logs secrets, only tool name/arguments/
    outcome (see agents.validation_copilot.ToolCallLogEntry)."""
    con = get_store_connection()
    session_id = get_session_id()
    now = datetime.utcnow()
    for i, call in enumerate(tool_calls, start=1):
        duckdb_store.save_copilot_tool_call(
            con, session_id, turn, i, call.tool_name, call.arguments, call.success, call.error, now
        )


def get_recent_tool_call_log(limit: int = 100) -> list[dict]:
    return duckdb_store.list_copilot_tool_calls(get_store_connection(), get_session_id(), limit=limit)
