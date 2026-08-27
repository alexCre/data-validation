# Claude Code Master Prompt — Agentic dMRV Data Validation PoC

You are building an end-to-end Proof of Concept for an **Agentic Data Validation system for a dMRV SaaS platform**.

The primary business objective is **improving data quality and verification readiness before data is submitted to a third-party Validation and Verification Body (VVB)**.

Secondary objectives are:
1. Reduce engineering effort when validation requirements change.
2. Demonstrate a credible, bounded agentic-AI capability.

Build the system, tests, sample data, documentation, and Streamlit UI end-to-end. Do not stop at scaffolding. Make reasonable implementation decisions when details are unspecified, document those decisions, and keep configuration editable.

---

## 1. Core product principle

The system must be:

> **Agentic where flexibility is valuable. Deterministic where auditability matters.**

There are **two bounded agentic roles**:

### A. Rule Authoring Agent
The user writes a validation requirement in natural language. The agent:
- interprets the validation intent;
- understands the validation data schema and semantic catalog;
- identifies the required data fields and relationships;
- selects approved validation operators;
- composes those operators into a structured executable rule;
- returns one of:
  - `COMPILED`
  - `NEEDS_CLARIFICATION`
  - `UNSUPPORTED_CAPABILITY`

The agent **does not validate individual field records**.

### B. Capability Extension Agent
This role is triggered only when the Rule Authoring Agent returns `UNSUPPORTED_CAPABILITY`.

It:
- explains which part of the rule is already supported;
- identifies the missing capability;
- proposes a reusable new operator;
- defines the operator contract, typed inputs/outputs, parameters, edge cases, and proposed tests;
- can generate a **draft Python operator implementation and draft unit tests** for developer review.

Important:
- Generated operator code must **never be automatically executed, imported, registered, or activated**.
- Save generated code only to a clearly isolated `generated_drafts/` area.
- A developer must explicitly review and approve it before promotion into the active operator registry.
- Provide a developer-side promotion workflow/CLI that runs tests before copying an approved operator into the active codebase.
- Do not provide arbitrary runtime code execution through the normal rule-authoring path.

Actual data validation remains fully deterministic.

---

## 2. PoC constraints

### Input
The PoC will use a **filtered validation dataset supplied as CSV files**.

Do not depend on the production SaaS database.

The validation unit is:

`lot_id / field_id + season_id`

Assume records from different sources have reliable identifiers.

### LLM data boundary
The LLM should receive only:
- the user's natural-language validation rule;
- semantic schema;
- table/column descriptions;
- table relationships;
- valid categorical values/mappings when required;
- operator catalog and signatures;
- rule examples;
- for Capability Extension, the operator base interface/contract required to generate a draft.

Do **not** send record-level CSV rows to the LLM.

The deterministic engine has access to the CSV data locally.

### Technology
Use a deliberately simple local PoC stack:
- Python 3.11+
- Streamlit
- DuckDB
- Pydantic
- Pandas or Polars
- GeoPandas / Shapely where needed
- PyYAML
- pytest

Do not add:
- MCP
- LangGraph
- AutoGen
- a multi-agent framework
- Kubernetes
- a separate FastAPI backend
- a vector database
- autonomous SQL access by the LLM

The two agentic roles can share one normal LLM client/runtime.

---

## 3. Canonical validation data model

Design a canonical model that can later be mapped to real exported CSV columns.

Use separate logical tables because some data are one-to-many.

At minimum support:

### lots.csv
- `lot_id`
- `season_id`
- `farmer_id`
- `declared_area_ha`
- `geometry_geojson` or equivalent geometry string
- optional `geometry_crs`

### diaries.csv
- `lot_id`
- `season_id`
- `planting_date`
- `straw_management_date`
- `crop`

### photos.csv
- `photo_id`
- `lot_id`
- `season_id`
- `capture_date`
- `category`

### farmers.csv / contracts.csv
Either one or two tables, but support:
- `farmer_id`
- contract existence
- contract status such as `SIGNED`

### riceid.csv
- `lot_id`
- `season_id`
- `crop_class`

### lipa.csv
- `lot_id`
- `season_id`
- LIPA/DS26 membership flag or reference identifier

### seasons.csv
- `season_id`
- `start_date`
- `end_date`

Create a configurable **column mapping / adapter layer** so the real filtered CSV export can be mapped into the canonical model without rewriting the validation engine.

For geometry area:
- support GeoJSON stored in CSV;
- parse with Shapely;
- use a defensible area calculation;
- if CRS is geographic, reproject using GeoPandas to an equal-area CRS such as EPSG:6933 before calculating hectares;
- keep this configurable and document the assumption.

---

## 4. Initial C1–C11 rule pack

Implement these rules deterministically.

### C1
**Planting date must be after straw management date.**

### C2
**First photo is Installation or Non-rice.**
First means earliest by `capture_date`, not upload time.

### C3
**Consistency in Crop in Field Diary and Photo categories.**
Use an explicit configurable category mapping/ontology rather than literal string equality.

### C4
**Planting date must be within the season.**

### C5
**Non-rice field should not have other photos.**
Interpret this as:
- if the first photo category is `Non-rice`,
- there must be no subsequent photos for the same `lot_id + season_id`.

Keep this behavior configurable.

### C6
**Photo dates must be within the season.**
All applicable photo `capture_date` values must fall within the season date range.

### C7
**Consistency of Crop in Field Diary and RiceID.**
Use a configurable category mapping.

### C8
**Lot has GeoJSON.**

### C9
**Consistency of farmer declared area and GeoJSON area.**
Use a configurable percentage tolerance.
Default PoC tolerance: `10%`.
Do not hard-code it into operator code; keep it in rule configuration.

### C10
**Lot has farmer with signed contract.**
Validate the relationship and status, not PDF contents.

### C11
**Lot is in LIPA 2025 DS26.**
For the initial PoC, model this as identifier/membership validation rather than spatial overlay unless input data explicitly requires spatial membership.

---

## 5. Validation result model

Every rule evaluation must return one of:

- `PASS`
- `FAIL`
- `REVIEW`
- `NOT_APPLICABLE`

The rule itself defines missing-data behavior.

Do not globally convert all missing values to FAIL.

Each result should persist at least:
- `validation_run_id`
- `lot_id`
- `season_id`
- `rule_id`
- `rule_version`
- `result`
- `severity`
- deterministic reason/explanation
- structured observations used by the rule
- evaluated timestamp

No LLM is required to generate these explanations.

Generate deterministic templates from the rule/operator result.

Field-season overall readiness:
- `FAILED` if one or more applicable rules are `FAIL`;
- `NEEDS_REVIEW` if no FAIL exists but one or more rules are `REVIEW`;
- `READY` if all applicable rules PASS or are NOT_APPLICABLE.

---

## 6. Rule DSL

Do not generate new Python code for ordinary rules.

Create a typed validation DSL using Pydantic.

A rule should include:
- `rule_id`
- `name`
- `version`
- `description`
- `scope`
- `severity`
- required inputs
- expression / operator tree
- missing-data behavior
- parameters
- active/draft status

Use an expression-tree representation that can compose operators.

Example concept:

```json
{
  "rule_id": "C1",
  "name": "Planting after straw management",
  "scope": "field_season",
  "expression": {
    "operator": "date_after",
    "args": [
      {"field": "diaries.planting_date"},
      {"field": "diaries.straw_management_date"}
    ]
  },
  "missing_data": "REVIEW"
}
```

The actual implementation may improve this format, but it must remain:
- typed;
- inspectable;
- serializable;
- versionable;
- validated against the operator registry before execution.

---

## 7. Initial operator registry

Implement reusable operators, not eleven one-off validation functions.

The initial library should be sufficient for C1–C11 and common unseen rules.

Suggested initial primitives:

### Temporal
- `date_before`
- `date_after`
- `date_between`
- `days_between`

### Categorical
- `equals`
- `not_equals`
- `in_set`
- `mapped_equals`

### Sequence / collection
- `first_by`
- `last_by`
- `filter`
- `count`
- `count_where`
- `exists`

### Logical
- `and`
- `or`
- `not`
- `if_then`

### Numeric
- `absolute_difference`
- `percentage_difference`
- `within_range`
- `less_than`
- `less_than_or_equal`
- `greater_than`

### Spatial
- `geometry_exists`
- `geometry_area_ha`
- `point_within_geometry` only if needed by sample rules

### Relational / document / membership
- `related_record_exists`
- `status_equals`
- `dataset_membership`

Each operator must expose metadata:
- operator name;
- category;
- description;
- typed inputs;
- output type;
- parameters;
- examples;
- deterministic execute function.

The agent's available operator catalog must be built dynamically from this registry.

---

## 8. Important operators that must NOT exist initially

Do not implement these initially, because they are reserved for Capability Gap testing:

- `classify_field_stage(photo)`
- `distance_to_boundary(...)`
- `validate_stage_progression(...)`

Do not create equivalent operators under different names that accidentally make the challenge rules compilable.

---

## 9. Three challenge rules for Capability Gap testing

Include these as documented fixtures/examples.

### Challenge Rule 1 — Visual crop-stage evidence
User input:

> A planting photo should visually show a field condition consistent with planting or early crop establishment.

Expected initial result:

`UNSUPPORTED_CAPABILITY`

Expected missing capability:

`classify_field_stage(photo)`

Reason:
The initial system has photo metadata/category validation but no image-content interpretation.

---

### Challenge Rule 2 — Representative photo location
User input:

> A geotagged photo must be inside the field and reasonably representative of the field, not captured too close to the field boundary.

Expected initial result:

`UNSUPPORTED_CAPABILITY`

Expected missing capability:

`distance_to_boundary(...)`

Reason:
A simple point-in-polygon operator cannot measure distance from the field boundary.

---

### Challenge Rule 3 — Plausible crop-stage progression
User input:

> Crop observations across the season must follow a plausible crop progression and must not move backwards, for example Harvest → Vegetative.

Expected initial result:

`UNSUPPORTED_CAPABILITY`

Expected missing capability:

`validate_stage_progression(...)`

Reason:
Generic sequence operators do not encode semantic crop-stage order.

Create automated tests asserting that all three return `UNSUPPORTED_CAPABILITY` with a sensible capability-gap specification in the initial implementation.

---

## 10. Rule Authoring Agent

Implement an LLM adapter behind a clean interface.

Use environment variables and never commit secrets.

Suggested interface:

```python
class RuleAuthoringAgent:
    def compile_rule(
        self,
        user_rule: str,
        semantic_catalog: SemanticCatalog,
        operator_catalog: OperatorCatalog,
    ) -> RuleCompilationResult:
        ...
```

`RuleCompilationResult` should support:

### COMPILED
Contains:
- structured rule;
- human-readable interpretation;
- required data;
- selected operators;
- assumptions;
- preview explanation.

### NEEDS_CLARIFICATION
Contains:
- understood portion;
- concise clarification question(s);
- ambiguity explanation.

### UNSUPPORTED_CAPABILITY
Contains:
- understood goal;
- supported parts;
- missing capability/capabilities;
- proposed reusable operator name(s);
- reason the current operator set is insufficient.

Use structured LLM output and validate it with Pydantic.

The agent may select and compose only operators that exist in the registry.

Never accept hallucinated operators as executable.

---

## 11. Capability Extension Agent

Implement a separate bounded workflow, but it can use the same LLM provider.

Suggested interface:

```python
class CapabilityExtensionAgent:
    def specify_gap(
        self,
        rule_text: str,
        compilation_result: RuleCompilationResult,
        operator_catalog: OperatorCatalog,
    ) -> CapabilityGapSpec:
        ...

    def generate_draft(
        self,
        gap_spec: CapabilityGapSpec,
        operator_interface: str,
    ) -> GeneratedOperatorDraft:
        ...
```

`CapabilityGapSpec` should include:
- missing capability;
- proposed operator name;
- purpose;
- reusable semantics;
- typed input contract;
- typed output contract;
- configuration parameters;
- edge cases;
- failure behavior;
- suggested unit tests;
- example rules that could reuse the operator.

`GeneratedOperatorDraft` should contain:
- draft Python implementation;
- draft unit tests;
- operator metadata;
- notes/assumptions.

Save drafts only under something like:

```text
generated_drafts/
  <operator_name>/
    operator.py
    test_operator.py
    metadata.yaml
    README.md
```

### Critical safety boundary
The Streamlit app must not import or execute these generated draft files.

Implement an explicit developer promotion script, for example:

```bash
python -m scripts.promote_operator generated_drafts/<operator_name>
```

Promotion should:
1. require an explicit confirmation flag or interactive confirmation;
2. run the draft's tests in a controlled test process;
3. refuse promotion if tests fail;
4. copy the approved implementation into the real operator package;
5. update/register metadata;
6. tell the developer to restart the app if needed.

Keep this practical for a local PoC. Do not build a full sandbox platform.

---

## 12. Semantic catalog

Create a semantic catalog separate from the raw CSV data.

It should describe:
- canonical tables;
- fields;
- field types;
- human-readable meanings;
- relationships;
- field-season scope;
- enums;
- category mappings;
- operator compatibility where useful.

The LLM uses this catalog, not sample rows.

Store it in editable YAML/JSON files.

Example:

```yaml
diaries:
  planting_date:
    type: date
    description: Farmer-reported planting date for the field-season.
  crop:
    type: enum
    description: Crop reported in the field diary.
    values:
      - Rice
      - Non-rice
      - Corn
```

Create separate category mapping configuration for C3 and C7.

---

## 13. Streamlit UI

Build a usable internal PoC, not a generic chatbot.

Main navigation should contain four primary pages:

### 1. Dashboard
Answer:

> Is this monitoring dataset ready for verification?

Show:
- total field-seasons;
- READY;
- NEEDS_REVIEW;
- FAILED;
- pass rate per rule;
- top validation issues;
- last validation run.

Provide `Run Validation`.

---

### 2. Data
Allow multiple CSV upload or loading a local sample-data folder.

Show:
- loaded sources;
- row counts;
- schema mapping status;
- basic source-data health;
- field-season count.

Do not expose the LLM here.

---

### 3. Rules
Show:
- C1–C11 and custom rules;
- status: Draft / Active / Disabled;
- version;
- severity;
- inputs/operators;
- test/activate controls.

Include an **Agentic Validation Rule Builder**:

1. text area: "Describe the validation requirement"
2. `Ask Agent`
3. show:
   - agent understanding;
   - data identified;
   - operators selected;
   - validation plan;
   - assumptions;
   - compilation status.
4. `Preview`
5. `Test Rule`
6. display result counts and example failures
7. `Save Draft`
8. `Activate`

If result is `UNSUPPORTED_CAPABILITY`, show a **Capability Gap** panel:
- what is supported;
- what is missing;
- suggested operator;
- `Generate Capability Specification`;
- optional developer-mode `Generate Operator Draft`.

The generated draft must only be saved for review.

A dedicated fifth page is not required; developer mode can live in the Rules page behind a setting such as `DEVELOPER_MODE=true`.

---

### 4. Field Review
Table-first interface.

Allow filtering by:
- rule;
- result;
- severity;
- lot/field;
- season.

Selecting one field-season should show:
- overall readiness;
- C1–C11/custom rule results;
- deterministic reason;
- observations that triggered the rule;
- relevant data-source values.

### CSV export
The Field Review page must allow users to download validation results as CSV.

Support two export modes:

#### A. Field Summary Export
One row per `lot_id / field_id + season_id`.

Include at minimum:
- `lot_id` or `field_id`
- `season_id`
- overall readiness/status
- failed rule IDs
- review rule IDs
- number of FAIL results
- number of REVIEW results
- primary issue / deterministic summary
- `validation_run_id`

#### B. Detailed Validation Export
One row per `lot_id / field_id + season_id + rule`.

Include at minimum:
- `lot_id` or `field_id`
- `season_id`
- `rule_id`
- `rule_version`
- `result`
- `severity`
- deterministic reason
- structured/serialized observed values where practical
- expected condition or rule description
- `validation_run_id`
- evaluation timestamp

Export behavior:
- exports must respect the active filters in Field Review;
- for example, if the user filters to `FAIL + C9 + DS26`, the downloaded CSV should contain only the matching records;
- also provide an option to export the full current validation run;
- CSV generation must be local and deterministic;
- do not involve the LLM in export generation;
- implement using Streamlit `st.download_button()` or an equivalent native Streamlit download flow.

No LLM investigation agent is needed in this PoC.

---

## 14. Rule lifecycle

Implement:

`DRAFT → TESTED → ACTIVE → DISABLED`

At minimum persist:
- rule ID;
- version;
- natural-language source requirement;
- structured DSL;
- author/creator if available;
- creation timestamp;
- activation timestamp;
- active status.

Do not overwrite old active rule definitions silently.

If a rule changes materially, create a new version.

---

## 15. Persistence

Use a local DuckDB database file for:
- rules;
- rule versions;
- validation runs;
- validation results;
- activation state;
- capability-gap records;
- generated-draft metadata.

CSV data may also be loaded into DuckDB for efficient joins.

The LLM must not be invoked during deterministic batch execution.

---

## 16. Synthetic dataset

Before the real CSV export exists, create reproducible synthetic CSV fixtures.

Generate at least:
- a small dataset for unit/integration tests;
- a larger dataset (e.g. 1,000+ field-seasons) for demo/performance testing.

Seed known failures for every C1–C11 rule.

Create an expected-results fixture so we can verify that the engine catches intentionally injected problems.

Examples:
- planting before straw management;
- first photo invalid;
- diary/photo crop conflict;
- planting outside season;
- Non-rice followed by later photos;
- photo outside season;
- diary/RiceID disagreement;
- missing geometry;
- area difference above tolerance;
- unsigned/missing contract;
- missing LIPA membership.

Use a fixed random seed.

---

## 17. Testing requirements

Use pytest extensively.

At minimum add:

### Operator unit tests
Every operator should have positive, negative, missing-data, and edge-case tests.

### C1–C11 rule tests
Test expected PASS / FAIL / REVIEW behavior.

### DSL validation tests
Reject:
- nonexistent operators;
- wrong argument types;
- invalid field references;
- malformed expressions.

### Agent compiler tests
Mock the LLM and verify:
- valid structured rules compile;
- hallucinated operator names are rejected;
- ambiguity returns `NEEDS_CLARIFICATION`;
- missing capabilities return `UNSUPPORTED_CAPABILITY`.

### LLM privacy-boundary test
Use a spy/mock client and verify that record-level CSV values are not included in the LLM payload.

### Challenge-rule tests
All three challenge rules must initially return `UNSUPPORTED_CAPABILITY`.

### Capability draft tests
Verify:
- draft files are written only to `generated_drafts`;
- generated draft files are not imported by the application;
- promotion refuses when tests fail.

### CSV export tests
Verify:
- Field Summary Export contains one row per filtered field-season;
- Detailed Validation Export contains one row per filtered field-season × rule;
- active Field Review filters are honored;
- full-run export is available;
- export generation does not invoke the LLM.

### Integration test
Load synthetic CSVs → run C1–C11 → persist results → query dashboard metrics → export filtered validation results to CSV.

---

## 18. Performance

The validation engine must evaluate in batch.

Do not call the LLM per field-season or per PASS/FAIL record.

Use DuckDB/vectorized Python operations where practical.

A reasonable PoC target is:
- 10,000 field-seasons × initial rules should complete comfortably on a normal laptop;
- avoid row-by-row Python loops when vectorized/DuckDB approaches are available.

Add a simple benchmark script and document observed performance rather than hard-coding a misleading guarantee.

Cache expensive derived values such as geometry area where appropriate.

---

## 19. Suggested repository structure

Use a structure similar to:

```text
dmrv-agentic-validation-poc/
├── app/
│   ├── streamlit_app.py
│   ├── pages/
│   │   ├── dashboard.py
│   │   ├── data.py
│   │   ├── rules.py
│   │   └── field_review.py
│   └── components/
│
├── validation/
│   ├── engine.py
│   ├── models.py
│   ├── result_models.py
│   ├── registry.py
│   ├── dsl/
│   └── operators/
│       ├── temporal.py
│       ├── categorical.py
│       ├── sequence.py
│       ├── logical.py
│       ├── numeric.py
│       ├── spatial.py
│       └── relational.py
│
├── agents/
│   ├── rule_authoring.py
│   ├── capability_extension.py
│   ├── models.py
│   ├── prompts.py
│   └── providers/
│
├── catalog/
│   ├── schema.yaml
│   ├── relationships.yaml
│   ├── category_mappings.yaml
│   └── operator_examples.yaml
│
├── rules/
│   ├── C1.yaml
│   ├── ...
│   └── C11.yaml
│
├── adapters/
│   ├── csv_adapter.py
│   └── canonical_mapping.py
│
├── persistence/
│   └── duckdb_store.py
│
├── synthetic/
│   ├── generate.py
│   └── expected_results/
│
├── generated_drafts/
│   └── .gitkeep
│
├── scripts/
│   ├── promote_operator.py
│   └── benchmark.py
│
├── tests/
│
├── docs/
│   ├── ARCHITECTURE.md
│   ├── RULE_DSL.md
│   ├── CAPABILITY_EXTENSION.md
│   └── CHALLENGE_RULES.md
│
├── .env.example
├── pyproject.toml
└── README.md
```

You may improve this layout if there is a strong reason, but preserve the separation between:
- deterministic validation;
- agentic rule authoring;
- capability-extension drafts;
- data adapters;
- semantic metadata.

---

## 20. LLM provider implementation

Create an abstraction such as:

```python
class LLMProvider(Protocol):
    def structured_generate(self, ...):
        ...
```

Implement at least:
- an Anthropic provider if `ANTHROPIC_API_KEY` is configured;
- a deterministic mock/fake provider for automated tests and offline demo development.

Use `.env.example`.

Do not commit credentials.

Make the model name configurable through an environment variable rather than hard-coding it deeply in the codebase.

The Streamlit app must remain usable for deterministic C1–C11 validation even when no LLM key is configured. In that case, disable agentic rule creation with a clear UI message while keeping the rest of the app functional.

---

## 21. Development sequence

Work in this order:

### Phase 1 — deterministic foundation
1. repository setup;
2. canonical data model;
3. semantic catalog;
4. operator interface + registry;
5. rule DSL;
6. C1–C11;
7. synthetic data;
8. deterministic tests;
9. batch validation engine;
10. DuckDB persistence.

Do not start with the LLM.

### Phase 2 — Streamlit validation product
11. Data page;
12. Dashboard;
13. Rules library;
14. Field Review;
15. Run Validation workflow.

### Phase 3 — Rule Authoring Agent
16. LLM provider;
17. structured rule compiler;
18. Preview → Test → Save Draft → Activate;
19. validation against schema/operator registry.

### Phase 4 — Capability Extension Agent
20. `UNSUPPORTED_CAPABILITY`;
21. capability-gap specification;
22. code/test draft generation;
23. safe isolated draft storage;
24. developer promotion workflow;
25. challenge-rule tests.

### Phase 5 — polish
26. README;
27. architecture documentation;
28. benchmark;
29. clean demo data;
30. end-to-end smoke test.

---

## 22. Definition of Done

The PoC is done only when all of the following work:

1. Streamlit launches locally with one command.
2. Synthetic CSV data can be loaded.
3. C1–C11 execute deterministically.
4. Dashboard summarizes verification readiness.
5. Field Review explains why a field-season failed.
6. A user can write a new simple rule in natural language.
7. The Rule Authoring Agent identifies fields/operators and composes a valid DSL rule.
8. The user can Preview → Test → Save → Activate the rule.
9. Activated rules participate in later deterministic validation runs.
10. No LLM call occurs per field-season.
11. Record-level CSV data are not sent to the LLM.
12. Unsupported rules return `UNSUPPORTED_CAPABILITY` rather than hallucinated code/operators.
13. The three challenge rules correctly trigger capability gaps.
14. Capability Extension Agent produces a reusable operator specification.
15. Developer mode can generate a draft implementation + tests into `generated_drafts/`.
16. Generated draft code is not automatically executed.
17. Promotion is explicit and test-gated.
18. Rule/result history is persisted in DuckDB.
19. Users can download a filtered **Field Summary CSV** from Field Review.
20. Users can download a filtered **Detailed Validation CSV** at rule-evaluation level.
21. CSV exports respect the active rule/result/severity/field/season filters and can also export the full validation run.
22. `pytest` passes.
23. README contains exact setup/run/test/demo instructions.

---

## 23. PoC narrative to preserve in the implementation

The product is **Agentic Data Validation for dMRV**.

The strongest message is:

> **The Validation Agent determines how a validation requirement should be checked. The Capability Extension Agent helps developers add missing reusable capabilities. The deterministic engine performs the actual field-level checks.**

This architecture is intentionally:
- flexible at rule authoring;
- extensible when new validation concepts appear;
- deterministic at execution;
- auditable for verification;
- lightweight enough for an internal PoC.

Do not turn this into an autonomous data-judging chatbot.

---

## 24. Working style for Claude Code

Please:
- inspect the repository before changing files;
- create a short implementation plan first;
- then implement in small, testable increments;
- run tests frequently;
- do not leave placeholder functions where working implementations are reasonable;
- document assumptions;
- prefer simple, readable architecture over abstractions that are not needed for the PoC;
- if exact real CSV column names are unknown, implement canonical adapters and sample mappings instead of blocking;
- if a business semantic is inherently ambiguous, expose it as configuration and document the default;
- keep the app runnable after each major phase.

Start by showing me:
1. the proposed repository structure;
2. the core Pydantic models for the DSL/operator registry;
3. the implementation plan by phase.

Then begin implementation.
