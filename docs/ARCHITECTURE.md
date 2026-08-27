# Architecture

## Core principle

Agentic where flexibility is valuable (rule authoring, capability gap
specification). Deterministic where auditability matters (every field-level
PASS/FAIL/REVIEW/NOT_APPLICABLE decision). No LLM call happens during batch
validation, and no record-level CSV data is ever sent to an LLM.

## Data flow

```
data/csv/*.csv --adapters.csv_adapter--> DuckDB (lots, diaries, photos, fertilizer_applications)
                                                |
                                                v
rules/*.yaml --validation.dsl.loader--> validation.models.Rule
                                                |
                                                v
                          validation.engine.run_batch
                          (build_field_season_contexts + evaluate per rule)
                                                |
                                                v
                          persistence.duckdb_store (rule_versions,
                          validation_runs, validation_results)
                                                |
                                                v
                          app/streamlit_app.py + app/pages/*
                          (Dashboard, Data, Rules, Field Review)
```

The Rule Authoring Agent and Capability Extension Agent (`agents/`) sit
beside this pipeline, not inside it: they only ever see
`catalog/schema.yaml` + the operator registry's metadata + the user's rule
text (see `agents/prompts.py` and `tests/test_llm_privacy_boundary.py`).
Their only way to affect the deterministic pipeline is by producing a typed
`Rule` that a developer/user explicitly saves and activates via the Rules
page - the engine never calls out to an LLM mid-run.

## Real dataset, not fabricated fixtures

`data/csv/` is a real filtered export (fields, field-diaries, field-photos
for both dry-crop season 3 and wet-crop season 4). Per an explicit
decision (see the approved plan), this PoC does **not** fabricate
`farmers`/`contracts`/`riceid`/`lipa` data - none of the active C1-C9 rules
depend on them, but they stay documented in the catalog schema (not in
`validation.engine.AVAILABLE_TABLES`) so a future rule referencing them is
recognized as legitimate rather than hallucinated, and would correctly
report `NOT_APPLICABLE` rather than being faked.

Season date boundaries (for C4/C7) also aren't in the export. Rather than
fabricate a `seasons.csv`, they're a documented, editable config default in
`catalog/season_bounds.yaml`, injected into each field-season's context as a
`season` pseudo-table by `validation.engine.build_field_season_contexts`.

## Key deviations from the original spec assumptions

1. **Geometry is WKT, not GeoJSON.** The source column is named `geojson`
   but contains WKT (`MULTIPOLYGON (((...)))`). `validation/operators/spatial.py`
   parses with `shapely.wkt.loads`.
2. **CRS is EPSG:4326** (confirmed from the coordinate ranges - Luzon, PH).
   Area (`geometry_area_ha`) is computed geodesically on the WGS84 ellipsoid
   via `pyproj.Geod.geometry_area_perimeter` directly on the EPSG:4326
   geometry, not by reprojecting to an equal-area planar CRS.
3. **Diary de-duplication.** `field-diaries-*.csv` is fanned out by a join
   with `field_fertilizer_application` (up to 12 rows per diary).
   `adapters/csv_adapter.py` selects `DISTINCT` on the diary-level columns.
4. **PII stripping is an allowlist, not a denylist**, applied at the
   adapter layer (`adapters/pii_policy.py`) before anything reaches DuckDB,
   the semantic catalog, or the UI. `owner_name` and `rice_specialist` are
   dropped; opaque IDs (`field_id`/`participant_id`) are kept as they
   aren't PII by themselves.
5. **`is_deleted = false`** is applied at CSV ingestion for `fields` and
   `photos` (both have the column); `diaries` doesn't have one.
6. **Photos with a blank `field_id`** (status `Pending Match`) are excluded
   - they have no lot to attach to.

## Performance approach

Rather than compiling the generic Pydantic expression DSL into fully
vectorized SQL, the engine does a single bulk fetch per table
(`build_field_season_contexts`) and then walks each rule's expression tree
in Python per field-season context. This avoids N+1 queries while keeping
the DSL simple to extend with new operators. Observed throughput on the
real ~32k-field-season dataset: see `scripts/benchmark.py` output (roughly
150k+ rule-evaluations/sec on a normal laptop as of this writing).

## PII policy

See `adapters/pii_policy.py` for the full allowlist. Any new column added
to a future export is excluded by default (allowlist, not denylist) until
someone explicitly adds it and confirms it isn't PII.
