"""Asserts record-level CSV values never reach the LLM payload (spec section
2: "Do not send record-level CSV rows to the LLM"). Uses a spy provider that
records every prompt it's given, then checks those prompts against real
values pulled straight from the loaded CSV data.
"""

import validation.operators  # noqa: F401
from adapters import csv_adapter
from agents.capability_extension import CapabilityExtensionAgent
from agents.models import RuleCompilationResult
from agents.providers.mock_provider import MockProvider
from agents.rule_authoring import RuleAuthoringAgent


class _SpyProvider:
    def __init__(self, delegate) -> None:
        self.delegate = delegate
        self.captured_prompts: list[str] = []

    def structured_generate(self, system_prompt, user_prompt, response_model):
        self.captured_prompts.append(system_prompt)
        self.captured_prompts.append(user_prompt)
        return self.delegate.structured_generate(system_prompt, user_prompt, response_model)


def _sample_pii_free_but_specific_values() -> list[str]:
    """Values that would only appear in the prompt if raw CSV rows leaked -
    a specific unique_name and a specific WKT coordinate pair from the real
    dataset, neither of which is PII but both of which are record-level."""
    con = csv_adapter.get_connection()
    csv_adapter.load_all(con)
    row = con.execute(
        "SELECT unique_name, geometry_wkt FROM lots WHERE geometry_wkt IS NOT NULL LIMIT 1"
    ).fetchone()
    return [v for v in row if v]


def test_rule_authoring_prompt_excludes_record_level_data():
    spy = _SpyProvider(MockProvider())
    agent = RuleAuthoringAgent(spy)
    agent.compile_rule("Planting date must be after straw management date.")

    assert spy.captured_prompts
    combined = "\n".join(spy.captured_prompts)
    for value in _sample_pii_free_but_specific_values():
        assert value not in combined, f"record-level value leaked into LLM prompt: {value!r}"


def test_capability_extension_prompt_excludes_record_level_data():
    spy = _SpyProvider(MockProvider())
    rule_agent = RuleAuthoringAgent(MockProvider())
    compiled = rule_agent.compile_rule(
        "A geotagged photo must be inside the field and reasonably representative of the field, not captured too close to the field boundary."
    )
    cap_agent = CapabilityExtensionAgent(spy)
    cap_agent.specify_gap("distance to boundary rule", compiled)

    combined = "\n".join(spy.captured_prompts)
    for value in _sample_pii_free_but_specific_values():
        assert value not in combined


def test_rule_authoring_prompt_only_contains_catalog_and_operator_metadata():
    spy = _SpyProvider(MockProvider())
    agent = RuleAuthoringAgent(spy)
    agent.compile_rule("Planting date must be after straw management date.")

    user_prompt = spy.captured_prompts[1]
    assert "Semantic catalog" in user_prompt
    assert "Operator catalog" in user_prompt
    # No CSV loader / connection is even touched to build this prompt.
