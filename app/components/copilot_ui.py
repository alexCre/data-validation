"""Shared Validation Copilot chat UI - rendered inside the popup dialog
opened by render_copilot_launcher(), a floating button embedded on
Dashboard and Field Review. Popup-only by design: no separate Copilot page
in the nav. See agents/validation_copilot.py for the actual agent loop;
this module is presentation only."""

from __future__ import annotations

import os

import pandas as pd
import streamlit as st
from streamlit.errors import StreamlitAPIException

from agents.providers.anthropic_provider import AnthropicProvider, is_configured
from agents.providers.mock_provider import MockProvider
from agents.validation_copilot import ValidationCopilot
from app.components.state import next_custom_rule_id
from copilot.service import build_default_registry
from copilot.state import (
    append_chat_history,
    append_display_turn,
    get_chat_history,
    get_display_turns,
    get_recent_tool_call_log,
    log_tool_calls,
    next_turn_number,
    reset_conversation,
)
from copilot.tools.rule_authoring import get_cached_compilation_result

EXAMPLE_PROMPTS = [
    "Why are so many fields failing?",
    "Show me C9 failures.",
    "Why did LOT-123437 fail?",
    "Show me the fertilizer application dates for LOT-123437.",
    "Download all failed field-seasons.",
    "Compare the latest run with the previous run.",
    "Create a rule that planting must be within 15 days after season start.",
]


def _rerun_here() -> None:
    """A bare st.rerun() always full-reruns the app, which - inside an
    st.dialog - dismisses the dialog before the new chat messages ever show.
    Prefer a fragment-scoped rerun (valid while genuinely inside the
    dialog's own rerun cycle) and fall back to a full rerun if called
    outside a dialog/fragment context."""
    try:
        st.rerun(scope="fragment")
    except StreamlitAPIException:
        st.rerun()


@st.cache_resource
def _get_registry():
    return build_default_registry()


def _get_copilot() -> ValidationCopilot:
    provider = AnthropicProvider() if is_configured() else MockProvider()
    return ValidationCopilot(provider, _get_registry())


def _build_attachment(tool_calls: list) -> dict | None:
    """Inspects a turn's tool calls for one the UI can turn into a concrete
    action (download button, hand off to Rules/Field Review)."""
    for call in tool_calls:
        if call.tool_name == "export_validation_csv" and call.success and call.output:
            return {"type": "export", **call.output}
        if call.tool_name == "request_new_rule" and call.success and call.output:
            return {"type": "rule_request", "rule_text": call.arguments.get("rule_text", ""), **call.output}
    rule_ids = {
        call.arguments.get("rule_id")
        for call in tool_calls
        if call.tool_name in {"get_validation_results", "get_top_validation_issues", "get_field_findings"}
        and call.arguments.get("rule_id")
    }
    if len(rule_ids) == 1:
        return {"type": "open_field_review", "rule_id": next(iter(rule_ids))}
    return None


def _render_tool_output(call) -> None:
    """Best-effort structured rendering (KPIs/tables) for a tool's output,
    instead of only the model's prose - shown for every successful call so
    the user sees the actual numbers behind the answer, not just a claim."""
    if not call.success or not call.output:
        return
    out = call.output
    if call.tool_name == "get_validation_summary":
        m1, m2, m3, m4 = st.columns(4)
        m1.metric("Total field-seasons", f"{out['total_field_seasons']:,}")
        m2.metric("READY", f"{out['ready_count']:,}")
        m3.metric("REVIEW_REQUIRED", f"{out['review_required_count']:,}")
        m4.metric("VALIDATION_FAILED", f"{out['validation_failed_count']:,}")
        if out["top_issues"]:
            st.dataframe(pd.DataFrame(out["top_issues"]), use_container_width=True, hide_index=True)
    elif call.tool_name in {"get_top_validation_issues"}:
        if out["issues"]:
            st.dataframe(pd.DataFrame(out["issues"]), use_container_width=True, hide_index=True)
    elif call.tool_name == "get_validation_results":
        if out["rows"]:
            st.dataframe(pd.DataFrame(out["rows"]), use_container_width=True, hide_index=True)
            if out["truncated"]:
                st.caption(
                    f"Showing {out['returned']} of {out['total_matching']:,} matching - refine or export for the rest."
                )
    elif call.tool_name == "get_field_source_records":
        if out["records"]:
            st.dataframe(pd.DataFrame(out["records"]), use_container_width=True, hide_index=True)
    elif call.tool_name == "get_field_findings":
        if out["findings"]:
            st.dataframe(
                pd.DataFrame(out["findings"])[["rule_id", "rule_name", "result", "reason"]],
                use_container_width=True,
                hide_index=True,
            )
    elif call.tool_name == "compare_validation_runs" and out.get("found"):
        m1, m2, m3 = st.columns(3)
        m1.metric("READY change", out["ready_change"])
        m2.metric("REVIEW_REQUIRED change", out["review_required_change"])
        m3.metric("VALIDATION_FAILED change", out["failed_change"])
        st.caption(f"{out['newly_failing_count']} newly failing, {out['resolved_count']} resolved.")
    elif call.tool_name == "get_validation_run_history" and out["runs"]:
        st.dataframe(pd.DataFrame(out["runs"]), use_container_width=True, hide_index=True)


def _render_attachment(attachment: dict) -> None:
    if attachment["type"] == "export":
        try:
            with open(attachment["file_path"], "rb") as f:
                data = f.read()
            st.download_button(
                f"⬇️ Download {attachment['file_name']} ({attachment['row_count']:,} rows)",
                data,
                file_name=attachment["file_name"],
                mime="text/csv",
                type="primary",
                key=f"dl_{attachment['file_name']}",
            )
        except OSError:
            st.warning("That export file is no longer available - ask again to regenerate it.")

    elif attachment["type"] == "open_field_review":
        if st.button("Open in Field Review", key=f"open_fr_{attachment['rule_id']}"):
            st.session_state["field_review_rule_filter"] = [attachment["rule_id"]]
            st.switch_page("pages/field_review.py")

    elif attachment["type"] == "rule_request":
        status = attachment.get("status")
        st.write(f"**Status:** {status}")
        if status == "COMPILED":
            st.success(f"✅ PASS — {attachment.get('pass_criteria')}")
            st.error(f"❌ FAIL — {attachment.get('fail_criteria')}")
            st.warning(f"🔍 NEEDS_REVIEW — {attachment.get('review_criteria')}")
        elif status == "NEEDS_CLARIFICATION":
            for q in attachment.get("clarification_questions", []):
                st.write(f"- {q}")
        elif status == "UNSUPPORTED_CAPABILITY":
            st.write("**Missing capability:**", ", ".join(attachment.get("missing_capabilities", [])))

        if status in {"COMPILED", "UNSUPPORTED_CAPABILITY"} and st.button(
            "Open in Rules to continue", key=f"open_rules_{attachment.get('request_id')}"
        ):
            cached = get_cached_compilation_result(attachment["request_id"])
            if cached is not None:
                st.session_state["compilation_result"] = cached
                st.session_state["requirement_text"] = attachment["rule_text"]
                st.session_state["interpretation_confirmed"] = False
                st.session_state["candidate_rule"] = None
                st.session_state["gap_spec"] = None
                st.session_state["candidate_rule_id"] = next_custom_rule_id()
                st.switch_page("pages/rules.py")
            else:
                st.warning("That rule request has expired - ask the Copilot to create it again.")


def render_copilot_chat() -> None:
    """The full Copilot chat surface: landing prompts, history, input, and
    (in Developer Mode) tool-call traces. Safe to call from a normal page
    body or from inside an st.dialog - it's pure session-state-driven."""
    developer_mode = os.environ.get("DEVELOPER_MODE", "false").lower() == "true"

    run_id = st.session_state.get("validation_run_id")
    if run_id is None:
        st.info("No validation run yet. Go to **Data & Setup** to select seasons and click Run Data Validation.")
        return

    if not is_configured():
        st.info(
            "ANTHROPIC_API_KEY is not set - using the offline mock Copilot (keyword-based heuristics, "
            "not a real LLM) so this stays usable for a demo. Deterministic C1-C9 validation elsewhere "
            "is unaffected either way."
        )

    display_turns = get_display_turns()
    pending_prompt = None
    if not display_turns:
        st.markdown("**Ask about your validation results.** Try:")
        cols = st.columns(2)
        for i, prompt in enumerate(EXAMPLE_PROMPTS):
            with cols[i % 2]:
                if st.button(prompt, key=f"example_{i}", use_container_width=True):
                    pending_prompt = prompt

    col_reset, _ = st.columns([1, 5])
    with col_reset:
        if display_turns and st.button("🔄 New conversation"):
            reset_conversation()
            _rerun_here()

    for turn in get_display_turns():
        with st.chat_message(turn["role"]):
            st.write(turn["text"])
            if turn["role"] == "assistant":
                if turn["tool_calls"]:
                    checked = ", ".join(sorted({c.tool_name for c in turn["tool_calls"]}))
                    st.caption(f"Checked: {checked}")
                    for call in turn["tool_calls"]:
                        _render_tool_output(call)
                if turn["attachment"]:
                    _render_attachment(turn["attachment"])
                if developer_mode and turn["tool_calls"]:
                    with st.expander("Developer: tool call trace"):
                        for call in turn["tool_calls"]:
                            st.json(
                                {
                                    "tool": call.tool_name,
                                    "arguments": call.arguments,
                                    "success": call.success,
                                    "error": call.error,
                                    "output": call.output,
                                }
                            )

    typed_prompt = st.chat_input("Ask about validation results, a specific field, or request a new rule...")
    user_prompt = pending_prompt or typed_prompt

    if user_prompt:
        turn_number = next_turn_number()
        append_chat_history("user", user_prompt)
        append_display_turn("user", user_prompt)

        with st.spinner("Checking validation results..."):
            result = _get_copilot().run(get_chat_history())

        append_chat_history("assistant", result.text)
        log_tool_calls(turn_number, result.tool_calls)
        attachment = _build_attachment(result.tool_calls)
        append_display_turn("assistant", result.text, tool_calls=result.tool_calls, attachment=attachment)
        _rerun_here()

    if developer_mode:
        with st.expander("Developer: full tool-call log (this session, persisted)"):
            log_rows = get_recent_tool_call_log()
            if log_rows:
                st.dataframe(pd.DataFrame(log_rows), use_container_width=True, hide_index=True)
            else:
                st.caption("No tool calls logged yet.")


@st.dialog("💬 Validation Copilot", width="large")
def _copilot_dialog() -> None:
    render_copilot_chat()


# Streamlit gives a widget's container the CSS class "st-key-<key>" when a
# key is set - used here to pin just this one button to the bottom-left
# corner, floating over page content, like a normal chat-widget launcher.
# z-index is set very high (not just 999) because Streamlit's sidebar sits
# in its own stacking context on the same (left) side of the screen - a
# merely-high z-index left it rendered but hidden behind the sidebar.
_FLOATING_BUTTON_CSS = """
<style>
.st-key-copilot_launcher_button {
    position: fixed;
    bottom: 1.5rem;
    left: 1.5rem;
    z-index: 999999;
    width: auto;
}
.st-key-copilot_launcher_button button {
    border-radius: 999px;
    box-shadow: 0 4px 14px rgba(0, 0, 0, 0.25);
    padding: 0.6rem 1.1rem;
}
</style>
"""


def render_copilot_launcher(label: str = "💬 Ask Validation Copilot") -> None:
    """A floating button (fixed to the bottom-left corner, like a normal
    chat-widget launcher) that opens the Copilot as a popup - the only way
    to reach it, since there's no separate Copilot page in the nav."""
    st.markdown(_FLOATING_BUTTON_CSS, unsafe_allow_html=True)
    if st.button(label, key="copilot_launcher_button"):
        _copilot_dialog()
