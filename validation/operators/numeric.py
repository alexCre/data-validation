from validation.registry import operator


@operator(
    "absolute_difference",
    category="numeric",
    description="Absolute difference |a - b|.",
    input_types=["number", "number"],
    output_type="number",
)
def absolute_difference(a, b) -> float | None:
    if a is None or b is None:
        return None
    return abs(a - b)


@operator(
    "percentage_difference",
    category="numeric",
    description=(
        "|a - b| / b * 100, i.e. a's percentage deviation from reference b. "
        "None if b is 0 or either value is missing."
    ),
    input_types=["number", "number"],
    output_type="number",
)
def percentage_difference(a, b) -> float | None:
    if a is None or b is None or b == 0:
        return None
    return abs(a - b) / abs(b) * 100


@operator(
    "within_range",
    category="numeric",
    description="True if x is within [low, high] inclusive.",
    input_types=["number", "number", "number"],
    output_type="bool",
)
def within_range(x, low, high) -> bool | None:
    if x is None or low is None or high is None:
        return None
    return low <= x <= high


@operator(
    "less_than",
    category="numeric",
    description="True if a < b.",
    input_types=["number", "number"],
    output_type="bool",
)
def less_than(a, b) -> bool | None:
    if a is None or b is None:
        return None
    return a < b


@operator(
    "less_than_or_equal",
    category="numeric",
    description="True if a <= b.",
    input_types=["number", "number"],
    output_type="bool",
)
def less_than_or_equal(a, b) -> bool | None:
    if a is None or b is None:
        return None
    return a <= b


@operator(
    "greater_than",
    category="numeric",
    description="True if a > b.",
    input_types=["number", "number"],
    output_type="bool",
)
def greater_than(a, b) -> bool | None:
    if a is None or b is None:
        return None
    return a > b
