import os
import sys
from datetime import datetime
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import streamlit as st
from pydantic import ValidationError

from agents.capability_extension import CapabilityExtensionAgent, save_draft
from agents.models import CompilationStatus
from agents.providers.anthropic_provider import is_configured
from agents.providers.mock_provider import MockProvider
from app.components.state import (
    delete_custom_rule,
    delete_static_rule,
    get_custom_rules,
    get_data_connection,
    get_rule_authoring_agent,
    get_rules,
    get_store_connection,
    next_custom_rule_id,
    promote_custom_rule,
)
from persistence import duckdb_store
from validation.dsl.validate import RuleValidationError
from validation.engine import build_field_season_contexts, evaluate_rule_for_context, AVAILABLE_TABLES
from validation.models import Rule, RuleStatus

st.title("Rules")

DEVELOPER_MODE = os.environ.get("DEVELOPER_MODE", "false").lower() == "true"

rules = get_rules(validate=False)
st.subheader("Base rule pack")
st.dataframe(
    [
        {
            "rule_id": r.rule_id,
            "name": r.name,
            "status": r.status.value,
            "version": r.version,
            "required_inputs": ", ".join(r.required_inputs),
            "operator": r.expression.operator,
            "missing_data_policy": r.missing_data.value,
        }
        for r in rules
    ],
    use_container_width=True,
    hide_index=True,
)

if rules:
    with st.expander("⚠️ Delete a base rule pack rule"):
        st.warning(
            "This permanently deletes `rules/<id>.yaml` from disk. This project has "
            "no git history here, so there is no undo - the rule is gone until someone "
            "re-authors and re-saves that YAML file by hand."
        )
        static_del_col1, static_del_col2 = st.columns([2, 1])
        with static_del_col1:
            static_rule_to_delete = st.selectbox(
                "Rule to delete",
                [r.rule_id for r in rules],
                format_func=lambda rid: f"{rid} - {next(r.name for r in rules if r.rule_id == rid)}",
                key="static_rule_to_delete",
            )
        with static_del_col2:
            st.write("")
            st.write("")
            confirm_static_delete = st.checkbox(f"I understand, permanently delete {static_rule_to_delete}")
            if st.button("🗑️ Permanently Delete", type="secondary", disabled=not confirm_static_delete):
                delete_static_rule(static_rule_to_delete)
                st.success(f"Deleted {static_rule_to_delete}.")
                st.rerun()

st.subheader("Custom rules (agent-authored)")
custom_rules = get_custom_rules()
if not custom_rules:
    st.caption("None yet - build one below.")
else:
    st.dataframe(
        [
            {
                "rule_id": r.rule_id,
                "name": r.name,
                "status": r.status.value,
                "version": r.version,
                "required_inputs": ", ".join(r.required_inputs),
                "operator": r.expression.operator,
                "missing_data_policy": r.missing_data.value,
            }
            for r in custom_rules
        ],
        use_container_width=True,
        hide_index=True,
    )
    manage_col1, manage_col2 = st.columns([2, 1])
    with manage_col1:
        selected_custom_rule = st.selectbox(
            "Manage a custom rule",
            [r.rule_id for r in custom_rules],
            format_func=lambda rid: f"{rid} - {next(r.name for r in custom_rules if r.rule_id == rid)}",
        )
    with manage_col2:
        st.write("")
        st.write("")
        promote_col, delete_col = st.columns(2)
        with promote_col:
            if st.button("⬆️ Promote", help="Write this rule to rules/<id>.yaml so it ships with the app permanently."):
                try:
                    promote_custom_rule(selected_custom_rule)
                    st.success(f"Promoted {selected_custom_rule} to the base rule pack (rules/{selected_custom_rule}.yaml).")
                    st.rerun()
                except RuleValidationError as e:
                    st.error(f"Couldn't promote {selected_custom_rule} - it fails DSL validation: {e}")
        with delete_col:
            if st.button("🗑️ Delete", type="secondary"):
                delete_custom_rule(selected_custom_rule)
                st.success(f"Deleted {selected_custom_rule}.")
                st.rerun()

st.divider()
st.header("Agentic Validation Rule Builder")

if not is_configured():
    st.info(
        "ANTHROPIC_API_KEY is not set - using the offline mock agent (keyword-based "
        "heuristics, not a real LLM) so this page stays usable for a demo. Deterministic "
        "C1-C9 validation on the other pages is unaffected either way."
    )

provider = "anthropic" if is_configured() else "mock"
requirement_text = st.text_area("Describe the validation requirement", height=100)


def _get_agent():
    agent = get_rule_authoring_agent() if provider == "anthropic" else None
    if agent is None:
        from agents.rule_authoring import RuleAuthoringAgent

        agent = RuleAuthoringAgent(MockProvider())
    return agent


def _compile_and_store(text: str) -> None:
    st.session_state["compilation_result"] = _get_agent().compile_rule(text)
    st.session_state["requirement_text"] = text
    # A fresh (or refined) compilation invalidates whatever was tested/staged
    # before - never let a stale candidate rule from a prior interpretation
    # get Saved/Activated.
    st.session_state["interpretation_confirmed"] = False
    st.session_state["candidate_rule"] = None
    st.session_state["gap_spec"] = None
    # Assigned once per compiled interpretation (not re-rolled on every Test
    # Rule click) so it stays stable until this rule is actually saved, and
    # reflects the next free slot after the last rule currently in the list.
    st.session_state["candidate_rule_id"] = next_custom_rule_id()


if st.button("Ask Agent") and requirement_text.strip():
    _compile_and_store(requirement_text)

result = st.session_state.get("compilation_result")
if result is not None:
    st.subheader("Agent response")
    st.write(f"**Status:** {result.status.value}")

    if result.status == CompilationStatus.COMPILED:
        st.write("**Assigned rule ID:**", st.session_state.get("candidate_rule_id"))
        st.write("**Interpretation:**", result.interpretation)
        st.write("**Data identified:**", ", ".join(result.required_inputs))
        st.write("**Assumptions:**")
        for a in result.assumptions:
            st.write(f"- {a}")

        st.markdown("**What determines the result:**")
        st.success(f"✅ **PASS** — {result.pass_criteria}")
        st.error(f"❌ **FAIL** — {result.fail_criteria}")
        st.warning(f"🔍 **NEEDS_REVIEW** — {result.review_criteria}")

        with st.expander("Technical details (operators + DSL expression)"):
            st.write("**Operators selected:**", ", ".join(result.selected_operators))
            st.json(result.expression.model_dump())

        if not st.session_state.get("interpretation_confirmed"):
            st.info("Please confirm this is what you meant before testing it against real data.")
            col_confirm, col_clarify = st.columns(2)
            with col_confirm:
                if st.button("✅ Yes, this is correct"):
                    st.session_state["interpretation_confirmed"] = True
                    st.rerun()
            with col_clarify:
                clarification = st.text_area(
                    "Not quite right? Explain what's wrong or what you actually meant",
                    key="clarification_text",
                    height=80,
                )
                if st.button("Refine interpretation") and clarification.strip():
                    refined_text = (
                        f"{st.session_state['requirement_text']}\n\n"
                        f"The agent's previous interpretation was: {result.interpretation}\n"
                        f"User clarification: {clarification.strip()}"
                    )
                    _compile_and_store(refined_text)
                    st.rerun()

        if st.session_state.get("interpretation_confirmed"):
            if st.button("Test Rule"):
                candidate = Rule(
                    rule_id=st.session_state["candidate_rule_id"],
                    name=st.session_state["requirement_text"][:60],
                    description=st.session_state["requirement_text"],
                    required_inputs=result.required_inputs,
                    expression=result.expression,
                    missing_data=result.suggested_missing_data_policy or "REVIEW",
                    status=RuleStatus.DRAFT,
                    source_text=st.session_state["requirement_text"],
                )
                con = get_data_connection()
                contexts = build_field_season_contexts(con)
                outcomes = []
                for (lot_id, season_id), ctx in list(contexts.items())[:2000]:
                    outcomes.append(
                        evaluate_rule_for_context(candidate, lot_id, season_id, ctx, "preview", datetime.utcnow())
                    )
                counts = {}
                for o in outcomes:
                    counts[o.result.value] = counts.get(o.result.value, 0) + 1
                st.session_state["candidate_rule"] = candidate
                st.write(
                    "**Result counts (sample of up to 2000 field-seasons):**",
                    {k: f"{v:,}" for k, v in counts.items()},
                )
                examples = [o for o in outcomes if o.result.value == "FAIL"][:5]
                if examples:
                    st.write("**Example failures:**")
                    st.dataframe([e.model_dump() for e in examples], use_container_width=True)

            if st.session_state.get("candidate_rule") is not None:
                col_a, col_b = st.columns(2)
                with col_a:
                    if st.button("Save Draft"):
                        duckdb_store.save_rule_version(get_store_connection(), st.session_state["candidate_rule"])
                        st.success("Saved as DRAFT.")
                with col_b:
                    if st.button("Activate"):
                        activated = st.session_state["candidate_rule"].model_copy(
                            update={"status": RuleStatus.ACTIVE, "activated_at": datetime.utcnow().isoformat()}
                        )
                        duckdb_store.save_rule_version(get_store_connection(), activated)
                        st.success("Activated. It will run on the next Run Data Validation.")

    elif result.status == CompilationStatus.NEEDS_CLARIFICATION:
        st.write("**Understood so far:**", result.understood_portion)
        st.write("**Ambiguity:**", result.ambiguity_explanation)
        for q in result.clarification_questions:
            st.write(f"- {q}")

    elif result.status == CompilationStatus.UNSUPPORTED_CAPABILITY:
        st.subheader("Capability Gap")
        st.write("**Understood goal:**", result.understood_goal)
        st.write("**Already supported:**", ", ".join(result.supported_parts) or "(none)")
        st.write("**Missing capability:**", ", ".join(result.missing_capabilities))
        st.write("**Suggested operator(s):**", ", ".join(result.proposed_operator_names))
        st.write("**Why unsupported:**", result.insufficiency_reason)

        def _get_capability_agent() -> CapabilityExtensionAgent:
            return CapabilityExtensionAgent(
                get_rule_authoring_agent()._provider if provider == "anthropic" else MockProvider()  # type: ignore[union-attr]
            )

        if st.button("Generate Capability Specification"):
            try:
                gap_spec = _get_capability_agent().specify_gap(st.session_state["requirement_text"], result)
                st.session_state["gap_spec"] = gap_spec
            except (RuntimeError, ValidationError) as e:
                st.error(f"Couldn't generate a capability specification: {e}")

        gap_spec = st.session_state.get("gap_spec")
        if gap_spec is not None:
            st.json(gap_spec.model_dump())

            if DEVELOPER_MODE and st.button("Generate Operator Draft (developer mode)"):
                try:
                    draft = _get_capability_agent().generate_draft(gap_spec)
                    target_dir = save_draft(draft, gap_spec)
                    st.success(f"Draft written to `{target_dir}` - not imported or executed by this app.")
                    st.code(draft.implementation_code, language="python")
                    st.code(draft.test_code, language="python")
                except (RuntimeError, ValidationError) as e:
                    st.error(f"Couldn't generate an operator draft: {e}")
            elif not DEVELOPER_MODE:
                st.caption("Set DEVELOPER_MODE=true to enable draft generation.")
