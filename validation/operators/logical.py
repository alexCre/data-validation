from validation.registry import operator


@operator(
    "and",
    category="logical",
    description="True if all args are true. None (unknown) propagates unless another arg is False.",
    input_types=["bool..."],
    output_type="bool",
)
def and_(*args) -> bool | None:
    if any(a is False for a in args):
        return False
    if any(a is None for a in args):
        return None
    return all(args)


@operator(
    "or",
    category="logical",
    description="True if any arg is true. None (unknown) propagates unless another arg is True.",
    input_types=["bool..."],
    output_type="bool",
)
def or_(*args) -> bool | None:
    if any(a is True for a in args):
        return True
    if any(a is None for a in args):
        return None
    return any(args)


@operator(
    "not",
    category="logical",
    description="Logical negation.",
    input_types=["bool"],
    output_type="bool",
)
def not_(a) -> bool | None:
    if a is None:
        return None
    return not a


@operator(
    "if_then",
    category="logical",
    description=(
        "Vacuously true when the condition is false; otherwise evaluates to "
        "the `then` branch. Used for conditional rules like 'if X then Y'."
    ),
    input_types=["bool", "bool"],
    output_type="bool",
)
def if_then(condition, then) -> bool | None:
    if condition is None:
        return None
    if condition is False:
        return True
    return then
