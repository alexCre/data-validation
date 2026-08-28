"""UI-level smoke tests for the Copilot page via Streamlit's AppTest -
exercised through the real entry point (app/streamlit_app.py) so
st.switch_page's relative paths resolve exactly as they do live. Forces
the offline mock provider (no ANTHROPIC_API_KEY) so these are deterministic
and make no real API calls, matching the rest of this test suite.
"""

from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

import validation.operators  # noqa: F401
from app.components.state import run_validation

ENTRY_POINT = str(Path(__file__).resolve().parents[1] / "app" / "streamlit_app.py")


@pytest.fixture
def no_api_key(monkeypatch):
    # Three separate patches, all needed:
    # 1. Deleting the env var alone isn't enough - anthropic_provider.py's
    #    module-level load_dotenv() silently refills any *missing* var from
    #    .env the next time that module is (re-)imported.
    # 2. Patching agents.providers.anthropic_provider.is_configured covers
    #    app/pages/copilot.py, since Streamlit re-execs a page's source
    #    fresh each AppTest .run() - its `from ... import is_configured`
    #    re-binds from the (now-patched) module each time.
    # 3. app.components.state is a normally-cached module (imported once,
    #    not re-exec'd per page run), so its own `is_configured` name - bound
    #    at state.py's first import - needs patching directly too.
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.setattr("agents.providers.anthropic_provider.is_configured", lambda: False)
    monkeypatch.setattr("app.components.state.is_configured", lambda: False)


@pytest.fixture(scope="module")
def run_id():
    return run_validation(season_ids=["3"])


def _launched_app(run_id) -> AppTest:
    at = AppTest.from_file(ENTRY_POINT)
    at.session_state["validation_run_id"] = run_id
    at.run(timeout=30)
    at.switch_page("pages/copilot.py")
    at.run(timeout=30)
    return at


def test_copilot_prompts_to_run_validation_first():
    at = AppTest.from_file(ENTRY_POINT)
    at.run(timeout=30)
    at.switch_page("pages/copilot.py")
    at.run(timeout=30)
    assert not at.exception
    assert any("Run Data Validation" in i.value for i in at.info)


def test_copilot_shows_example_prompts_on_landing(no_api_key, run_id):
    at = _launched_app(run_id)
    assert not at.exception
    assert len(at.button) >= 6


def test_copilot_answers_a_question_and_logs_tool_calls(no_api_key, run_id):
    at = _launched_app(run_id)
    at.chat_input[0].set_value("Why are so many fields failing?").run(timeout=30)
    assert not at.exception
    turns = at.session_state["copilot_display_turns"]
    assert turns[0]["role"] == "user"
    assert turns[1]["role"] == "assistant"
    assert turns[1]["tool_calls"][0].tool_name == "get_validation_summary"


def test_copilot_export_offers_download_button(no_api_key, run_id):
    at = _launched_app(run_id)
    at.chat_input[0].set_value("Download the fields failing C6.").run(timeout=30)
    assert not at.exception
    assert len(at.download_button) == 1


def test_copilot_rule_request_hands_off_to_rules_page(no_api_key, run_id):
    at = _launched_app(run_id)
    at.chat_input[0].set_value(
        "Create a rule that planting date must be after straw management date."
    ).run(timeout=30)
    assert not at.exception
    open_buttons = [b for b in at.button if "Open in Rules" in b.label]
    assert len(open_buttons) == 1
    open_buttons[0].click().run(timeout=30)
    assert not at.exception
    assert "compilation_result" in at.session_state
    assert at.session_state["requirement_text"]


def test_new_conversation_resets_state(no_api_key, run_id):
    at = _launched_app(run_id)
    at.chat_input[0].set_value("Why are so many fields failing?").run(timeout=30)
    assert at.session_state["copilot_display_turns"]
    reset_button = [b for b in at.button if "New conversation" in b.label][0]
    reset_button.click().run(timeout=30)
    assert at.session_state["copilot_display_turns"] == []
