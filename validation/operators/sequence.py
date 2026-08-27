"""Operators over one-to-many collections (e.g. a lot's photos).

`first_by`/`last_by`/`count` operate on an already-resolved list of item
dicts plus a plain field-name parameter. `filter`/`count_where`/`exists`
additionally receive an unevaluated predicate expression node, the engine's
per-item evaluate function, and the base context - the engine special-cases
these (see validation.engine) rather than pre-resolving their predicate arg,
since the predicate must run once per collection item.
"""

from validation.registry import operator


def _sort_key(item: dict, key_field: str):
    value = item.get(key_field)
    return (value is None, value)


@operator(
    "first_by",
    category="sequence",
    description="The item with the minimum value of key_field (e.g. earliest capture_date).",
    input_types=["list[record]"],
    output_type="record",
    parameters={"key_field": "str"},
)
def first_by(items: list, key_field: str):
    candidates = [i for i in items if i.get(key_field) is not None]
    if not candidates:
        return None
    return min(candidates, key=lambda i: _sort_key(i, key_field))


@operator(
    "last_by",
    category="sequence",
    description="The item with the maximum value of key_field.",
    input_types=["list[record]"],
    output_type="record",
    parameters={"key_field": "str"},
)
def last_by(items: list, key_field: str):
    candidates = [i for i in items if i.get(key_field) is not None]
    if not candidates:
        return None
    return max(candidates, key=lambda i: _sort_key(i, key_field))


@operator(
    "count",
    category="sequence",
    description="Number of items in the collection.",
    input_types=["list[record]"],
    output_type="int",
)
def count(items: list) -> int:
    return len(items)


def _predicate_results(items: list, predicate_node, evaluate_fn, base_context) -> list:
    return [evaluate_fn(predicate_node, {**base_context, "item": i}) for i in items]


@operator(
    "filter",
    category="sequence",
    description=(
        "Items where the predicate is explicitly True (engine-special-cased). "
        "Items where the predicate is unknown (None, e.g. missing data) are "
        "excluded, same as False - filtering can't act on uncertainty."
    ),
    input_types=["list[record]", "expression"],
    output_type="list[record]",
)
def filter_(items: list, predicate_node, evaluate_fn, base_context) -> list:
    results = _predicate_results(items, predicate_node, evaluate_fn, base_context)
    return [i for i, r in zip(items, results) if r is True]


@operator(
    "count_where",
    category="sequence",
    description="Count of items where the predicate is explicitly True (engine-special-cased).",
    input_types=["list[record]", "expression"],
    output_type="int",
)
def count_where(items: list, predicate_node, evaluate_fn, base_context) -> int:
    results = _predicate_results(items, predicate_node, evaluate_fn, base_context)
    return sum(1 for r in results if r is True)


@operator(
    "exists",
    category="sequence",
    description=(
        "True if any item's predicate is explicitly True; None (unknown) if "
        "no item is True but at least one is unknown (e.g. missing data), "
        "so the missing-data policy - not a false negative - decides the "
        "rule outcome; False only if every item's predicate is explicitly "
        "False (engine-special-cased)."
    ),
    input_types=["list[record]", "expression"],
    output_type="bool",
)
def exists(items: list, predicate_node, evaluate_fn, base_context) -> bool | None:
    results = _predicate_results(items, predicate_node, evaluate_fn, base_context)
    if any(r is True for r in results):
        return True
    if any(r is None for r in results):
        return None
    return False


@operator(
    "exists_ignoring_unknown",
    category="sequence",
    description=(
        "Like `exists`, but an item whose predicate is unknown (None, e.g. "
        "a record with a missing date) is ignored rather than making the "
        "whole result unknown, as long as at least one OTHER item resolves "
        "the predicate to True or False. Only returns None (unknown) when "
        "every item's predicate is unknown - i.e. there is no usable "
        "information at all, not just one incomplete record among others. "
        "Use where an incomplete record shouldn't block a conclusion "
        "already supported by the rest of the collection (engine-"
        "special-cased)."
    ),
    input_types=["list[record]", "expression"],
    output_type="bool",
)
def exists_ignoring_unknown(items: list, predicate_node, evaluate_fn, base_context) -> bool | None:
    if not items:
        return False
    results = _predicate_results(items, predicate_node, evaluate_fn, base_context)
    known = [r for r in results if r is not None]
    if any(r is True for r in known):
        return True
    if known:
        return False
    return None


@operator(
    "is_non_decreasing",
    category="sequence",
    description=(
        "True if items, ordered by order_field, have non-decreasing values "
        "of value_field (e.g. fertilizer applications recorded out of date "
        "sequence: 2nd applied_date before 1st). None (unknown) if fewer "
        "than two items carry both fields."
    ),
    input_types=["list[record]"],
    output_type="bool",
    parameters={"order_field": "str", "value_field": "str"},
)
def is_non_decreasing(items: list, order_field: str, value_field: str) -> bool | None:
    candidates = [i for i in items if i.get(order_field) is not None and i.get(value_field) is not None]
    if len(candidates) < 2:
        return None
    ordered = sorted(candidates, key=lambda i: i[order_field])
    values = [i[value_field] for i in ordered]
    return all(a <= b for a, b in zip(values, values[1:]))
