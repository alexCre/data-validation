from validation.registry import operator


@operator(
    "equals",
    category="categorical",
    description="True if a equals b.",
    input_types=["any", "any"],
    output_type="bool",
)
def equals(a, b) -> bool | None:
    if a is None or b is None:
        return None
    return a == b


@operator(
    "not_equals",
    category="categorical",
    description="True if a does not equal b.",
    input_types=["any", "any"],
    output_type="bool",
)
def not_equals(a, b) -> bool | None:
    if a is None or b is None:
        return None
    return a != b


@operator(
    "is_present",
    category="categorical",
    description=(
        "True if the value is present (not None/missing), False if it is "
        "missing. Deliberately does NOT propagate unknown like other "
        "operators - checking whether a field was recorded at all is the "
        "point, so this always resolves to a definite answer. Use this "
        "(not equals/not_equals against a null literal, which always "
        "returns unknown) for 'field X must be present/recorded' rules."
    ),
    input_types=["any"],
    output_type="bool",
)
def is_present(a) -> bool:
    return a is not None


@operator(
    "in_set",
    category="categorical",
    description="True if a is a member of the given set of values.",
    input_types=["any"],
    output_type="bool",
    parameters={"values": "list[any]"},
)
def in_set(a, values: list) -> bool | None:
    if a is None:
        return None
    return a in values


@operator(
    "mapped_equals",
    category="categorical",
    description=(
        "True if b is one of the values that source-category `a` maps to, "
        "using a configured category mapping (e.g. diary crop -> photo "
        "category ontology)."
    ),
    input_types=["any", "any"],
    output_type="bool",
    parameters={"mapping": "dict[str, list[str]]"},
)
def mapped_equals(a, b, mapping: dict) -> bool | None:
    if a is None or b is None:
        return None
    allowed = mapping.get(a, [])
    return b in allowed
