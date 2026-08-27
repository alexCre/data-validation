from __future__ import annotations

from enum import StrEnum
from typing import Any, Union

from pydantic import BaseModel, Field, field_validator


class FieldRef(BaseModel):
    """Reference to a canonical field, e.g. "diaries.planting_date"."""

    field: str


class Literal(BaseModel):
    value: Any


class ExpressionNode(BaseModel):
    operator: str
    args: list["Arg"] = Field(default_factory=list)
    params: dict[str, Any] = Field(default_factory=dict)


Arg = Union[ExpressionNode, FieldRef, Literal]
ExpressionNode.model_rebuild()


class RuleStatus(StrEnum):
    DRAFT = "DRAFT"
    TESTED = "TESTED"
    ACTIVE = "ACTIVE"
    DISABLED = "DISABLED"


class MissingDataPolicy(StrEnum):
    PASS = "PASS"
    FAIL = "FAIL"
    REVIEW = "REVIEW"
    NOT_APPLICABLE = "NOT_APPLICABLE"


class Rule(BaseModel):
    rule_id: str
    name: str
    version: int = 1
    description: str
    scope: str = "field_season"
    required_inputs: list[str] = Field(default_factory=list)
    expression: ExpressionNode
    missing_data: MissingDataPolicy = MissingDataPolicy.REVIEW
    parameters: dict[str, Any] = Field(default_factory=dict)
    status: RuleStatus = RuleStatus.DRAFT
    source_text: str | None = None
    created_at: str | None = None
    activated_at: str | None = None

    @field_validator("version")
    @classmethod
    def _version_positive(cls, v: int) -> int:
        if v < 1:
            raise ValueError("version must be >= 1")
        return v
