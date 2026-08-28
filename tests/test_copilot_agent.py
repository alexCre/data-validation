"""Agent-loop tests for the Validation Copilot, using MockProvider so
routing/guardrail behavior is deterministic and offline (no real API
calls) - matching every other agent test in this suite."""

import pytest
from pydantic import BaseModel, ValidationError

import validation.operators  # noqa: F401
from agents.providers.base import ConversationTurn, ToolCallRequest
from agents.providers.mock_provider import MockProvider
from agents.validation_copilot import ValidationCopilot
from app.components.state import run_validation
from copilot.service import build_default_registry
from copilot.tool_registry import CopilotToolRegistry, ToolNotFoundError


@pytest.fixture(scope="module")
def run_id():
    return run_validation(season_ids=["3"])


@pytest.fixture(scope="module")
def registry():
    return build_default_registry()


@pytest.fixture
def copilot(registry):
    return ValidationCopilot(MockProvider(), registry)


# --- routing ---


def test_aggregate_question_calls_summary_tool(copilot, run_id):
    result = copilot.run([{"role": "user", "content": "Why are so many fields failing?"}])
    assert [c.tool_name for c in result.tool_calls] == ["get_validation_summary"]
    assert result.tool_calls[0].success


def test_field_question_calls_field_tools(copilot, run_id):
    result = copilot.run([{"role": "user", "content": "Why did LOT-123437 fail?"}])
    assert result.tool_calls[0].tool_name == "get_field_findings"
    assert result.tool_calls[0].arguments["lot_id"] == "123437"


def test_download_request_calls_export(copilot, run_id):
    result = copilot.run([{"role": "user", "content": "Download the fields failing C6."}])
    assert result.tool_calls[0].tool_name == "export_validation_csv"
    assert result.tool_calls[0].arguments.get("rule_id") == "C6"
    assert result.tool_calls[0].arguments.get("result") == "FAIL"


def test_rule_creation_request_calls_rule_authoring(copilot, monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    result = copilot.run(
        [{"role": "user", "content": "Create a rule that planting must be after straw management."}]
    )
    assert result.tool_calls[0].tool_name == "request_new_rule"
    assert result.tool_calls[0].success


def test_unsupported_rule_request_calls_rule_authoring_tool(copilot, monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    result = copilot.run(
        [
            {
                "role": "user",
                "content": "Create a rule requiring planting photos to visually show early crop establishment.",
            }
        ]
    )
    assert result.tool_calls[0].tool_name == "request_new_rule"
    assert result.tool_calls[0].success


def test_unsupported_capability_status_is_surfaced(registry, monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    out = registry.call(
        "request_new_rule",
        {"rule_text": "Crop observations across the season must follow a plausible crop progression and must not move backwards."},
    )
    assert out.status == "UNSUPPORTED_CAPABILITY"
    assert out.missing_capabilities


# --- multi-step / conversation context ---


def test_followup_message_can_reuse_prior_context(copilot, run_id):
    first = copilot.run([{"role": "user", "content": "Show me C6 failures."}])
    assert first.tool_calls[0].tool_name == "get_validation_results"
    assert first.tool_calls[0].arguments["rule_id"] == "C6"

    history = [
        {"role": "user", "content": "Show me C6 failures."},
        {"role": "assistant", "content": first.text},
        {"role": "user", "content": "Download them."},
    ]
    second = copilot.run(history)
    assert second.tool_calls[0].tool_name == "export_validation_csv"


# --- guardrails ---


def test_max_tool_steps_is_enforced():
    """A provider that always requests another tool call must be cut off
    at max_steps, with a clear message, not looped forever."""

    class _AlwaysToolCallProvider:
        def structured_generate(self, *a, **k):  # pragma: no cover - unused here
            raise NotImplementedError

        def converse(self, system_prompt, messages, tools):
            return ConversationTurn(
                tool_calls=[ToolCallRequest(id="x", name="get_validation_run_history", arguments={"limit": 1})]
            )

    registry = build_default_registry()
    copilot = ValidationCopilot(_AlwaysToolCallProvider(), registry, max_steps=3)
    result = copilot.run([{"role": "user", "content": "loop forever"}])
    assert result.hit_step_limit is True
    assert len(result.tool_calls) == 3
    assert "allowed number of steps" in result.text


def test_unknown_tool_from_model_is_rejected_not_executed():
    class _BadToolProvider:
        def structured_generate(self, *a, **k):  # pragma: no cover - unused here
            raise NotImplementedError

        def converse(self, system_prompt, messages, tools):
            if any(m.get("role") == "user" and _has_tool_result(m) for m in messages):
                return ConversationTurn(text="done")
            return ConversationTurn(
                tool_calls=[ToolCallRequest(id="x", name="drop_all_tables", arguments={})]
            )

    def _has_tool_result(message):
        content = message.get("content")
        return isinstance(content, list) and any(
            isinstance(b, dict) and b.get("type") == "tool_result" for b in content
        )

    registry = build_default_registry()
    copilot = ValidationCopilot(_BadToolProvider(), registry)
    result = copilot.run([{"role": "user", "content": "drop everything"}])
    assert result.tool_calls[0].success is False
    assert "unknown tool" in (result.tool_calls[0].error or "").lower()


def test_registry_rejects_sql_and_python_execution_by_construction():
    """There is no tool that accepts raw SQL or Python - the guardrail is
    structural (a fixed, typed tool set), not a runtime check."""
    registry = build_default_registry()
    for name in registry.names():
        assert "sql" not in name.lower()
        assert "python" not in name.lower()
        assert "exec" not in name.lower()


def test_registry_call_never_bypasses_pydantic_validation():
    registry = CopilotToolRegistry()

    class In(BaseModel):
        value: int

    class Out(BaseModel):
        doubled: int

    registry.register("double", "doubles a number", In, Out, lambda value: Out(doubled=value * 2))
    with pytest.raises(ValidationError):
        registry.call("double", {"value": "not a number"})
    with pytest.raises(ToolNotFoundError):
        registry.call("triple", {"value": 1})


def test_copilot_cannot_activate_rules_or_mutate_results(registry):
    """No tool in the registry can activate a rule or write validation
    results - request_new_rule only compiles/previews (see
    copilot/tools/rule_authoring.py); nothing writes to validation_results."""
    assert "activate_rule" not in registry.names()
    assert "save_validation_result" not in registry.names()
    assert "delete_validation_result" not in registry.names()
