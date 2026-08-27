# Capability Extension Agent

Triggered only after the Rule Authoring Agent (`agents/rule_authoring.py`)
returns `UNSUPPORTED_CAPABILITY`. Two steps, both LLM-backed but bounded:

1. **`specify_gap`** - produces a `CapabilityGapSpec` (purpose, typed
   input/output contract, config parameters, edge cases, failure behavior,
   suggested unit tests, example rules that would reuse it).
2. **`generate_draft`** (developer-mode only) - produces a
   `GeneratedOperatorDraft`: implementation code + pytest tests + metadata.

## Safety boundary

`agents.capability_extension.save_draft` writes **only** under
`generated_drafts/<operator_name>/`:

```
generated_drafts/<operator_name>/
  operator.py
  test_operator.py
  metadata.yaml
  README.md
```

Nothing under `generated_drafts/` is ever imported or executed by the
Streamlit app or the validation engine -
`tests/test_agents.py::test_generated_drafts_are_never_imported_by_the_app`
statically checks every file under `app/` for an import of `generated_drafts`.

## Promotion

A developer explicitly runs:

```bash
python -m scripts.promote_operator generated_drafts/<operator_name> --yes
```

This: runs the draft's own tests in an isolated `pytest` subprocess first;
refuses to promote if they fail
(`tests/test_promote_operator.py::test_promotion_refuses_when_tests_fail`);
otherwise appends the implementation to `validation/operators/promoted.py`
(imported by `validation/operators/__init__.py`, so a restart of the
Streamlit app picks up the new operator). Without `--yes` it prompts
interactively before writing anything.

This is intentionally a thin, practical script for a local PoC - not a
sandboxed execution platform.
