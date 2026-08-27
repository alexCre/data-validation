# Agentic dMRV Data Validation PoC

A Proof of Concept for agentic data validation on a dMRV SaaS platform:
deterministic C1-C9 field-season validation over a real filtered CSV
export, plus two bounded agentic roles (Rule Authoring, Capability
Extension) for extending the rule set without hand-writing Python.

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
**Run Data Validation**. Then browse Dashboard / Rules / Field Review. No LLM
calls happen unless you use the Agentic Validation Rule Builder on the Rules
page.

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

90 tests: operator unit tests, C1-C9 rule tests against the real dataset,
DSL validation (rejects hallucinated operators/fields), agent-compiler
tests (mocked LLM), the LLM privacy-boundary spy test, the three
challenge-rule fixtures, CSV export tests, promotion-workflow tests, and an
end-to-end integration test.

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

## Known data-quality artifacts (not bugs)

The real dataset contains genuine defects - e.g. a handful of `planting_date`
values with garbage years (`0204-11-20`). These are intentionally left as-is
so C4/C6/C7 can be observed catching them, rather than being cleaned in the
adapter.

## Repository layout

See `docs/ARCHITECTURE.md` for the data-flow diagram. Top-level:
`adapters/` (real-CSV -> canonical DuckDB), `catalog/` (semantic
catalog/category mappings/season config), `validation/` (DSL, operator
registry, engine), `rules/` (C1-C9 YAML), `agents/` (Rule Authoring +
Capability Extension), `persistence/` (DuckDB store), `app/` (Streamlit),
`generated_drafts/` (agent-generated, never imported), `scripts/`
(promotion + benchmark), `tests/`, `docs/`.
