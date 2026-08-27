"""Static validation of a Rule's expression tree against the operator
registry and the semantic catalog's known fields.

Used both as a pytest-level guard (reject malformed/hallucinated rules) and
by the Rule Authoring Agent's compiler, which must never accept an operator
or field the agent hallucinated.
"""

from __future__ import annotations

from validation.models import ExpressionNode, FieldRef, Literal, Rule
from validation.registry import registry


class RuleValidationError(Exception):
    def __init__(self, errors: list[str]) -> None:
        self.errors = errors
        super().__init__("; ".join(errors))


def validate_rule(rule: Rule, known_fields: set[str]) -> list[str]:
    errors: list[str] = []
    _validate_node(rule.expression, known_fields, errors)
    return errors


def _validate_node(node: ExpressionNode | FieldRef | Literal, known_fields: set[str], errors: list[str]) -> None:
    if isinstance(node, Literal):
        return
    if isinstance(node, FieldRef):
        table = node.field.split(".", 1)[0]
        if table == "item":
            return  # predicate-scope field; schema depends on enclosing collection
        if node.field not in known_fields:
            errors.append(f"unknown field reference: {node.field!r}")
        return
    if isinstance(node, ExpressionNode):
        if not registry.has(node.operator):
            errors.append(f"unknown operator: {node.operator!r}")
            return
        spec = registry.get_spec(node.operator)
        # first_by/last_by/count take a single collection arg plus plain
        # (non-expression) params, not a 1:1 input_types<->args mapping.
        if node.operator not in {"first_by", "last_by", "count"}:
            expected = len(spec.input_types)
            variadic = expected and spec.input_types[-1].endswith("...")
            if not variadic and len(node.args) != expected:
                errors.append(
                    f"operator {node.operator!r} expects {expected} args, got {len(node.args)}"
                )
        for arg in node.args:
            _validate_node(arg, known_fields, errors)
        return
    errors.append(f"malformed expression node: {node!r}")
