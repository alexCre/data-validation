# Challenge rules (capability-gap fixtures)

Three natural-language requirements the initial operator registry
deliberately cannot compile, per the master spec (section 9). Reserved
operators `classify_field_stage`, `distance_to_boundary`, and
`validate_stage_progression` do not exist anywhere in
`validation/operators/` (enforced by `tests/test_challenge_rules.py`,
including a keyword scan that guards against smuggling in an equivalent
operator under a different name).

| # | Requirement | Expected result | Missing capability |
|---|---|---|---|
| 1 | "A planting photo should visually show a field condition consistent with planting or early crop establishment." | `UNSUPPORTED_CAPABILITY` | `classify_field_stage(photo)` - no image-content interpretation exists, only photo metadata/category. |
| 2 | "A geotagged photo must be inside the field and reasonably representative of the field, not captured too close to the field boundary." | `UNSUPPORTED_CAPABILITY` | `distance_to_boundary(...)` - `point_within_geometry` exists but can't measure distance from a boundary. |
| 3 | "Crop observations across the season must follow a plausible crop progression and must not move backwards, for example Harvest -> Vegetative." | `UNSUPPORTED_CAPABILITY` | `validate_stage_progression(...)` - generic sequence operators don't encode semantic crop-stage order. |

Covered end-to-end (compile -> UNSUPPORTED_CAPABILITY -> specify_gap ->
generate_draft -> save_draft under `generated_drafts/` only) in
`tests/test_agents.py` and `tests/test_challenge_rules.py`, using the
offline `MockProvider` so these tests run without an API key.
