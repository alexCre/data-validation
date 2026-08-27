import shutil

import pytest
from pydantic import BaseModel

import validation.operators  # noqa: F401
from agents.capability_extension import CapabilityExtensionAgent, save_draft
from agents.models import CompilationStatus, RuleCompilationResult
from agents.providers.mock_provider import MockProvider
from agents.rule_authoring import RuleAuthoringAgent
from validation.models import ExpressionNode, FieldRef


@pytest.fixture
def mock_agent():
    return RuleAuthoringAgent(MockProvider())


def test_compiles_simple_after_rule(mock_agent):
    result = mock_agent.compile_rule("Planting date must be after straw management date.")
    assert result.status == CompilationStatus.COMPILED
    assert result.expression.operator == "date_after"
    assert "diaries.planting_date" in result.required_inputs


def test_ambiguous_rule_needs_clarification(mock_agent):
    result = mock_agent.compile_rule("The data should generally look reasonable.")
    assert result.status == CompilationStatus.NEEDS_CLARIFICATION
    assert result.clarification_questions


@pytest.mark.parametrize(
    "rule_text,expected_operator",
    [
        (
            "A planting photo should visually show a field condition consistent with planting or early crop establishment.",
            "classify_field_stage",
        ),
        (
            "A geotagged photo must be inside the field and reasonably representative of the field, not captured too close to the field boundary.",
            "distance_to_boundary",
        ),
        (
            "Crop observations across the season must follow a plausible crop progression and must not move backwards, for example Harvest to Vegetative.",
            "validate_stage_progression",
        ),
    ],
)
def test_challenge_rules_return_unsupported_capability(mock_agent, rule_text, expected_operator):
    result = mock_agent.compile_rule(rule_text)
    assert result.status == CompilationStatus.UNSUPPORTED_CAPABILITY
    assert result.proposed_operator_names == [expected_operator]


class _HallucinatingProvider:
    """A fake LLM that returns a COMPILED result referencing an operator
    that doesn't exist in the registry - must be rejected, not executed."""

    def structured_generate(self, system_prompt, user_prompt, response_model):
        return RuleCompilationResult(
            status=CompilationStatus.COMPILED,
            expression=ExpressionNode(
                operator="totally_made_up_operator",
                args=[FieldRef(field="diaries.planting_date")],
            ),
            interpretation="hallucinated",
            required_inputs=["diaries.planting_date"],
            selected_operators=["totally_made_up_operator"],
            pass_criteria="n/a",
            fail_criteria="n/a",
            review_criteria="n/a",
        )


def test_hallucinated_operator_is_rejected():
    agent = RuleAuthoringAgent(_HallucinatingProvider())
    result = agent.compile_rule("anything")
    assert result.status == CompilationStatus.NEEDS_CLARIFICATION
    assert "totally_made_up_operator" in result.clarification_questions[0]


def test_compiled_result_requires_plain_language_explanations():
    with pytest.raises(ValueError, match="pass_criteria"):
        RuleCompilationResult(status=CompilationStatus.COMPILED, interpretation="ok")


class _IncompleteCompiledProvider:
    """Simulates a real provider whose structured output failed schema
    validation (e.g. COMPILED without the required explanation fields) -
    the agent must degrade gracefully, not crash the caller."""

    def structured_generate(self, system_prompt, user_prompt, response_model):
        return response_model(status=CompilationStatus.COMPILED)


def test_malformed_provider_response_degrades_to_needs_clarification():
    agent = RuleAuthoringAgent(_IncompleteCompiledProvider())
    result = agent.compile_rule("anything")
    assert result.status == CompilationStatus.NEEDS_CLARIFICATION


def test_capability_extension_specify_and_draft_writes_only_under_generated_drafts(tmp_path):
    agent = RuleAuthoringAgent(MockProvider())
    compiled = agent.compile_rule(
        "Crop observations across the season must follow a plausible crop progression and must not move backwards."
    )
    assert compiled.status == CompilationStatus.UNSUPPORTED_CAPABILITY

    cap_agent = CapabilityExtensionAgent(MockProvider())
    gap_spec = cap_agent.specify_gap(
        "Crop observations across the season must follow a plausible crop progression and must not move backwards.",
        compiled,
    )
    draft = cap_agent.generate_draft(gap_spec)

    target_dir = save_draft(draft, gap_spec, drafts_dir=tmp_path)
    try:
        assert target_dir.parent == tmp_path
        assert (target_dir / "operator.py").exists()
        assert (target_dir / "test_operator.py").exists()
        assert (target_dir / "metadata.yaml").exists()
        assert (target_dir / "README.md").exists()
    finally:
        shutil.rmtree(target_dir, ignore_errors=True)


def test_generated_drafts_are_never_imported_by_the_app():
    import ast
    from pathlib import Path

    repo_root = Path(__file__).resolve().parents[1]
    for py_file in (repo_root / "app").rglob("*.py"):
        tree = ast.parse(py_file.read_text())
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                names = [a.name for a in node.names]
            elif isinstance(node, ast.ImportFrom):
                names = [node.module or ""]
            else:
                continue
            assert not any(n.startswith("generated_drafts") for n in names), py_file
