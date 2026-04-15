"""Validation result models — frozen value types for schema compliance."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum

PASS_THRESHOLD: float = 0.90
PARTIAL_THRESHOLD: float = 0.70


class ValidationStatus(StrEnum):
    """Schema compliance verdict."""

    PASS = "pass"
    PARTIAL = "partial"
    FAIL = "fail"


def status_from_score(score: float) -> ValidationStatus:
    """Map a [0.0, 1.0] compliance score to a status label."""
    if score >= PASS_THRESHOLD:
        return ValidationStatus.PASS
    if score >= PARTIAL_THRESHOLD:
        return ValidationStatus.PARTIAL
    return ValidationStatus.FAIL


@dataclass(slots=True, frozen=True)
class ValidationIssue:
    """Single rule violation detected by a validator."""

    rule: str
    message: str


@dataclass(slots=True)
class ValidationResult:
    """Aggregate outcome of validating one backend response."""

    status: ValidationStatus
    score: float
    validator_name: str
    issues: list[ValidationIssue] = field(default_factory=list)
