# PII policy

Per an explicit project instruction, no possible PII enters the validation
database. This is enforced as an **allowlist**, not a denylist, in
`adapters/pii_policy.py`: only columns explicitly listed there are ever
selected out of the raw CSV export. Any new/unrecognized column in a future
export is excluded by default until someone reviews it and adds it.

## Excluded (raw source columns, never loaded)

- `owner_name` (fields source) - the farmer's name.
- `rice_specialist` (fields source) - a staff member's name.
- `taken_by_user_id` / `reviewed_by_user_id` / `reviewed_by_user_account_id`
  (photos source) - identify individual staff accounts; not needed by
  C1-C9 either, so dropped for minimality as well as privacy.

## Kept (not treated as PII)

- `field_id` / `participant_id` -> canonical `lot_id` / `farmer_id`. Opaque
  numeric identifiers issued by the source system, not names or contact
  info by themselves.
- `unique_name` - a field/plot code (e.g. `"1410"`, `"DAL-18-051"`), not a
  person's name.
- `ia` / `tsag` / `irrisystem` -> `irrigators_association` / `tsag` /
  `irrigation_system` - names of associations/groups/systems, not
  individuals.
- Geometry (`geojson`/WKT), area figures, dates, categories - none of these
  identify a person.

## Where it's applied

`adapters/csv_adapter.py` builds every canonical table (`lots`, `diaries`,
`photos`, `fertilizer_applications`) from a `SELECT` that only ever names
allowlisted columns (see
`_select_allowed`) - PII stripping happens before a single row reaches
DuckDB, so it can't leak downstream into the semantic catalog, the LLM
prompts (which don't touch CSV data at all - see
`docs/ARCHITECTURE.md`), the Streamlit UI, or the CSV exports.

Enforced by `tests/test_csv_adapter.py::test_lots_no_pii_columns`.
