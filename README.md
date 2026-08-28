# Agentic dMRV Data Validation PoC

A Proof of Concept for agentic data validation on a dMRV SaaS platform:
deterministic C1-C9 field-season validation over a real filtered CSV
export, plus three bounded agentic roles - **Rule Authoring** and
**Capability Extension** for extending the rule set without hand-writing
Python, and the **Validation Copilot**, a conversational layer for querying
results, inspecting fields, exporting CSVs, and requesting new rules (see
[Validation Copilot](#validation-copilot) below). None of the three decides
a validation outcome or activates a rule on their own - that stays
deterministic and gated behind the existing Preview → Test → Approve →
Activate flow.

See `docs/ARCHITECTURE.md` for the full design and the deviations from the
original spec forced by the real dataset (WKT vs GeoJSON, no
farmers/contracts/riceid/lipa source data, etc).

## Setup

Requires Python 3.11+.

```bash
python3.11 -m venv .venv
source .venv/bin/activate
pip install -e .
```

(Optional, for the real LLM-backed agents) copy `.env.example` to `.env` and
set `ANTHROPIC_API_KEY`. Without it, the app falls back to an offline mock
agent - deterministic C1-C9 validation is unaffected either way.

## Run

```bash
source .venv/bin/activate
streamlit run app/streamlit_app.py
```

Open the app (it lands on Data & Setup by default), select season(s), click
**Run Data Validation**. Then browse Dashboard / Field Review / Rules /
Copilot. No LLM calls happen unless you use the Agentic Validation Rule
Builder on the Rules page or ask the Copilot something.

## Deploy (Streamlit Community Cloud)

Repo: https://github.com/alexCre/data-validation

1. Go to [share.streamlit.io](https://share.streamlit.io) and sign in (log
   in with GitHub if prompted).
2. **New app** → pick this repo, branch `main`, main file path
   `app/streamlit_app.py`.
3. Before/after deploying, open the app's **Settings → Secrets** in the
   Streamlit Cloud UI and add:
   ```toml
   ANTHROPIC_API_KEY = "sk-ant-..."
   ```
   Never commit this to the repo - `.env` is gitignored and only used for
   local runs. Without this secret set, the deployed app falls back to the
   offline mock agent on the Rules page (deterministic C1-C9 validation
   works either way).
4. `requirements.txt` and `runtime.txt` (Python 3.11) are already in the
   repo root for Streamlit Cloud's build step.

**Known limitations of this deployment shape** (see `docs/ARCHITECTURE.md`
for more): the DuckDB store (`dmrv_validation.duckdb`) lives on local
container storage, which most PaaS hosts (including Community Cloud) treat
as ephemeral - custom/activated rules saved via the Rules page may not
survive a redeploy or container restart. Promote a rule you want to keep
into the permanent rule pack instead (Rules page → Custom rules → ⬆️
Promote), which writes a `rules/<id>.yaml` file that ships with the code.
There is also no per-user auth or rate limiting - anyone with the deployed
URL can trigger real Anthropic API calls billed to whatever key is set in
Secrets; set a spending cap on that key in the Anthropic Console as a
backstop.

## Test

```bash
source .venv/bin/activate
python -m pytest
```

144 tests: operator unit tests, C1-C9 rule tests against the real dataset,
DSL validation (rejects hallucinated operators/fields), agent-compiler
tests (mocked LLM), the LLM privacy-boundary spy test, the three
challenge-rule fixtures, CSV export tests, promotion-workflow tests, an
end-to-end integration test, and the Copilot's tool/agent/page tests (see
[Testing the Copilot](#testing-the-copilot)).

## Benchmark

```bash
source .venv/bin/activate
python -m scripts.benchmark
```

Reports observed throughput on the real ~32k-field-season dataset.

## Demo script

1. **Data & Setup** - select season(s) and click Run Data Validation; also
   see the loaded sources, the PII-stripped column allowlist, and the
   explicit note that `farmers`/`contracts`/`riceid`/`lipa` aren't present
   in this export and no active rule (C1-C9) depends on them.
2. **Dashboard** - see READY/NEEDS_REVIEW/FAILED counts and per-rule pass
   rates from the run you just kicked off.
3. **Rules** - browse C1-C9. In the Rule Builder, try:
   - `"Planting date must be after straw management date."` -> COMPILED
   - `"Crop observations across the season must follow a plausible crop
     progression and must not move backwards."` -> UNSUPPORTED_CAPABILITY;
     click Generate Capability Specification to see the
     `CapabilityGapSpec`. With `DEVELOPER_MODE=true`, also try Generate
     Operator Draft, then promote it from a terminal:
     `python -m scripts.promote_operator generated_drafts/<name> --yes`
4. **Field Review** - filter by rule/readiness/season, field identity
   (name/TSAG/IA/RIS), or minimum failure/NEEDS_REVIEW counts; inspect a
   field-season's deterministic reasons (including what data is missing, if
   any), download the Field Summary and Detailed Validation CSV exports
   (respecting active filters, or the full run).
5. **Copilot** - ask it things like *"Why are so many fields failing?"*,
   *"Show me C9 failures."*, *"Why did LOT-123437 fail?"* (then a follow-up
   like *"What about C9?"*), *"Download the fields failing C6."*, or
   *"Create a rule that planting must be after straw management."* - the
   last one lands on the Rules page with the compiled rule ready to
   Preview/Test/Activate, never activated automatically.

## Validation Copilot

An additional, on-demand conversational layer (`app/pages/copilot.py`) on
top of the existing Dashboard/Data & Setup/Rules/Field Review - it never
replaces them, never decides a validation outcome (PASS/FAIL/REVIEW/
NOT_APPLICABLE stay outputs of the deterministic engine), and never
activates a rule itself.

**How it works**: the Copilot is a bounded tool-use loop
(`agents/validation_copilot.py`, max 5 steps per message) over a fixed,
typed tool registry (`copilot/tool_registry.py` + `copilot/tools/*.py`) -
never arbitrary SQL/Python, never direct DuckDB/filesystem access. Every
tool call is Pydantic-validated before it runs; an unknown tool name or
invalid arguments are rejected, not executed. Large result sets are capped
(`get_validation_results` maxes out at 200 rows/page) or exported straight
to a local CSV file (`export_validation_csv`) - raw record data is never
dumped into the LLM's context, only structured summaries/counts.

**The 10 tools**, each reusing an existing service rather than duplicating
query logic (`app/components/state.py`, `app/components/exports.py`,
`persistence/duckdb_store.py`, `agents/rule_authoring.py`):
`get_validation_summary`, `get_top_validation_issues`,
`get_validation_results`, `get_field_validation_summary`,
`get_field_findings`, `get_rule_details`, `compare_validation_runs`,
`get_validation_run_history`, `export_validation_csv`, and
`request_new_rule` (hands off to the existing Rule Authoring Agent -
returns COMPILED/NEEDS_CLARIFICATION/UNSUPPORTED_CAPABILITY, same as the
Rules page; a "Open in Rules to continue" button carries the compiled
result over to the Rules page's own Preview → Test → Approve → Activate
flow, which is untouched and still required before anything runs live).

**Conversation state**: session-local only (`copilot/state.py`, Streamlit
`session_state`) - no long-term or cross-user memory. Follow-ups ("What
about C9?", "Only DS26") work because the plain user/assistant text history
is replayed to the model each turn; the per-turn tool-call exchange itself
stays internal to that turn so it never leaks orphaned tool blocks into
later requests.

**Logging**: every tool call (name, arguments, success/error, never
secrets) is persisted to DuckDB (`copilot_tool_calls` table) and shown in a
"Developer: tool call trace" expander when `DEVELOPER_MODE=true`. Normal
users see a plain `Checked: <tool names>` line, never raw arguments/output
or chain-of-thought.

**Offline fallback**: without `ANTHROPIC_API_KEY`, the Copilot page still
works via `agents/providers/mock_provider.py`'s deterministic keyword
routing (e.g. "download"/"export" → `export_validation_csv`, "why did
LOT-X fail" → `get_field_findings`, "create a rule" → `request_new_rule`) -
enough to demo the mechanism and to keep this repo's tests fully offline.
If the Copilot's LLM call fails for any reason (network, bad key, rate
limit), the page shows a plain error message inline; it never crashes the
app, and Dashboard/Data & Setup/Rules/Field Review are completely
unaffected either way (they don't depend on the Copilot at all).

### Testing the Copilot

```bash
pytest tests/test_copilot_tools.py   # each tool in isolation, real data, no LLM
pytest tests/test_copilot_agent.py   # routing, multi-step, guardrails - MockProvider, no network
pytest tests/test_copilot_page.py    # UI-level via Streamlit's AppTest, MockProvider, no network
```

All Copilot tests run offline (they force the mock provider even if
`ANTHROPIC_API_KEY` is set locally, matching every other agent test in this
suite) - `pytest` alone runs all of them along with everything else.

## Known data-quality artifacts (not bugs)

The real dataset contains genuine defects - e.g. a handful of `planting_date`
values with garbage years (`0204-11-20`). These are intentionally left as-is
so C4/C6/C7 can be observed catching them, rather than being cleaned in the
adapter.

## Repository layout

See `docs/ARCHITECTURE.md` for the data-flow diagram. Top-level:
`adapters/` (real-CSV -> canonical DuckDB), `catalog/` (semantic
catalog/category mappings/season config), `validation/` (DSL, operator
registry, engine), `rules/` (C1-C9 YAML), `agents/` (Rule Authoring,
Capability Extension, Validation Copilot, and shared LLM providers),
`copilot/` (the Copilot's tool models/registry/tools/session state - see
[Validation Copilot](#validation-copilot)), `persistence/` (DuckDB store),
`app/` (Streamlit: `pages/dashboard.py`, `data.py`, `rules.py`,
`field_review.py`, `copilot.py`), `generated_drafts/` (agent-generated,
never imported), `scripts/` (promotion + benchmark), `tests/`, `docs/`.
