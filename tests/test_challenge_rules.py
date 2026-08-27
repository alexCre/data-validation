"""The three capability-gap fixtures from the master spec (section 9). Each
must be rejected with UNSUPPORTED_CAPABILITY by the Rule Authoring Agent
because the operator registry deliberately lacks the operators these rules
would need (classify_field_stage, distance_to_boundary,
validate_stage_progression - see section 8 of the spec).

Phase 3 wires the actual LLM-backed compiler; these tests assert the
structural precondition it depends on (the reserved operators genuinely
don't exist) so a future compiler bug can't silently make these compilable.
"""

import validation.operators  # noqa: F401
from validation.registry import registry

RESERVED_OPERATORS = {
    "classify_field_stage",
    "distance_to_boundary",
    "validate_stage_progression",
}

CHALLENGE_RULES = [
    (
        "visual_crop_stage_evidence",
        "A planting photo should visually show a field condition consistent "
        "with planting or early crop establishment.",
        "classify_field_stage",
    ),
    (
        "representative_photo_location",
        "A geotagged photo must be inside the field and reasonably "
        "representative of the field, not captured too close to the field "
        "boundary.",
        "distance_to_boundary",
    ),
    (
        "plausible_crop_stage_progression",
        "Crop observations across the season must follow a plausible crop "
        "progression and must not move backwards, for example Harvest -> "
        "Vegetative.",
        "validate_stage_progression",
    ),
]


def test_reserved_operators_are_not_registered():
    for name in RESERVED_OPERATORS:
        assert not registry.has(name), (
            f"{name!r} must not exist in the initial operator registry - it's "
            "reserved for Capability Gap testing (spec section 8)."
        )


def test_no_equivalent_operator_smuggled_in_under_another_name():
    # A regression guard for "do not create equivalent operators under
    # different names that accidentally make the challenge rules
    # compilable" (spec section 8). Nothing in the registry should claim to
    # interpret image content, measure distance to a boundary, or validate
    # a semantic stage sequence.
    disallowed_keywords = {"classify", "image_content", "distance_to", "stage_progression"}
    for spec in registry.catalog():
        haystack = f"{spec.name} {spec.description}".lower()
        for keyword in disallowed_keywords:
            assert keyword not in haystack, (
                f"operator {spec.name!r} looks like it smuggles in a reserved "
                f"capability via keyword {keyword!r}"
            )
