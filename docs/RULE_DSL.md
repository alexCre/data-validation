# Rule DSL

A rule (`validation.models.Rule`) is a typed, serializable, versionable
Pydantic object with an `expression` tree of `ExpressionNode` / `FieldRef` /
`Literal` nodes. Rules live as YAML in `rules/*.yaml` and are loaded via
`validation.dsl.loader.load_all_rules`, which validates every rule against
the operator registry and the semantic catalog before returning it
(`validation.dsl.validate.validate_rule`) - a rule referencing an unknown
operator or field is rejected at load time, not silently ignored.

## Node types

- `{operator: "...", args: [...], params: {...}}` - `ExpressionNode`. `args`
  are themselves nodes (recursively evaluated); `params` are plain values
  passed straight to the operator's Python implementation (e.g.
  `first_by`'s `key_field`, `in_set`'s `values`).
- `{field: "table.column"}` - `FieldRef`. Resolved against the current
  field-season context. A bare `{field: "photos"}` (no dot) resolves to the
  whole one-to-many collection.
- `{value: ...}` - `Literal`.

## Three-valued logic

Every operator returns `True`, `False`, or `None` (unknown/missing data),
never raises on missing input. If a rule's whole expression evaluates to
`None`, the engine applies the rule's `missing_data` policy
(`PASS`/`FAIL`/`REVIEW`/`NOT_APPLICABLE`) - see `validation/engine.py`.
This is deliberate: **do not** treat every missing value as `FAIL`. `and`/`or`
propagate `None` the same way SQL three-valued logic does (`False AND None
= False`, `True OR None = True`, `None` otherwise).

Sequence operators (`filter`/`count_where`/`exists`) apply the same
three-valued logic across a collection: `exists` returns `True` if any item
is a definite match, `None` if none match but at least one is unknown, and
`False` only if every item is a definite non-match.

## Predicate-scoped fields

Inside a `filter`/`count_where`/`exists` predicate, `{field: "item.category"}`
resolves against the current collection item, not the top-level context.

## Adding a new rule

1. Write it as YAML under `rules/`, following the pattern of `rules/C1.yaml`.
2. If it needs a crop/category mapping, add it to
   `catalog/category_mappings.yaml` and reference it via
   `params: {mapping: "$mapping_name"}` (resolved at load time, see
   `validation.dsl.loader._resolve_mapping_refs`).
3. `python -c "from validation.dsl.loader import load_all_rules; load_all_rules()"`
   will raise `RuleValidationError` if anything is wrong.
4. Add it to `tests/test_rules.py` with an assertion against the real
   dataset (or a small hand-built context, see `tests/test_agents.py` for
   the pattern of constructing a `Rule` directly in Python).

## Adding a new operator

Register it with `validation.registry.operator(...)` in the appropriate
`validation/operators/<category>.py` module (see any existing operator for
the pattern), and import the module from `validation/operators/__init__.py`
if it's a new file. Every operator needs positive, negative, and
missing-data test cases in `tests/test_operators.py`.
