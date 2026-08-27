from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field


class ResultStatus(StrEnum):
    PASS = "PASS"
    FAIL = "FAIL"
    REVIEW = "REVIEW"
    NOT_APPLICABLE = "NOT_APPLICABLE"


class Readiness(StrEnum):
    READY = "READY"
    NEEDS_REVIEW = "NEEDS_REVIEW"
    FAILED = "FAILED"


class ValidationResult(BaseModel):
    validation_run_id: str
    lot_id: str
    season_id: str
    rule_id: str
    rule_version: int
    result: ResultStatus
    reason: str
    observations: dict[str, Any] = Field(default_factory=dict)
    missing_inputs: list[str] = Field(default_factory=list)
    evaluated_at: datetime


def compute_readiness(results: list[ValidationResult]) -> Readiness:
    applicable = [r for r in results if r.result != ResultStatus.NOT_APPLICABLE]
    if any(r.result == ResultStatus.FAIL for r in applicable):
        return Readiness.FAILED
    if any(r.result == ResultStatus.REVIEW for r in applicable):
        return Readiness.NEEDS_REVIEW
    return Readiness.READY
