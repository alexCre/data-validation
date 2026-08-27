from __future__ import annotations

from typing import Any, Callable

from pydantic import BaseModel


class OperatorSpec(BaseModel):
    name: str
    category: str
    description: str
    input_types: list[str]
    output_type: str
    parameters: dict[str, str] = {}
    examples: list[dict[str, Any]] = []

    model_config = {"arbitrary_types_allowed": True}


class OperatorRegistry:
    """Holds deterministic operator implementations and their metadata.

    "Sequence" category operators (filter/count_where/exists) are special:
    their second argument is an unevaluated predicate expression, evaluated
    per collection item by the engine rather than resolved up front. Their
    `execute` receives `(items, predicate_node, evaluate_fn, base_context)`.
    Every other operator's `execute` receives already-resolved plain values.
    """

    def __init__(self) -> None:
        self._specs: dict[str, OperatorSpec] = {}
        self._executors: dict[str, Callable[..., Any]] = {}

    def register(self, spec: OperatorSpec, execute: Callable[..., Any]) -> None:
        if spec.name in self._specs:
            raise ValueError(f"operator already registered: {spec.name}")
        self._specs[spec.name] = spec
        self._executors[spec.name] = execute

    def get_executor(self, name: str) -> Callable[..., Any]:
        if name not in self._executors:
            raise KeyError(f"unknown operator: {name}")
        return self._executors[name]

    def get_spec(self, name: str) -> OperatorSpec:
        return self._specs[name]

    def has(self, name: str) -> bool:
        return name in self._specs

    def catalog(self) -> list[OperatorSpec]:
        return list(self._specs.values())


registry = OperatorRegistry()


def operator(
    name: str,
    category: str,
    description: str,
    input_types: list[str],
    output_type: str,
    parameters: dict[str, str] | None = None,
    examples: list[dict[str, Any]] | None = None,
):
    def decorator(fn: Callable[..., Any]) -> Callable[..., Any]:
        spec = OperatorSpec(
            name=name,
            category=category,
            description=description,
            input_types=input_types,
            output_type=output_type,
            parameters=parameters or {},
            examples=examples or [],
        )
        registry.register(spec, fn)
        return fn

    return decorator
