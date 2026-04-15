"""Retry engine models — strictness levels, failure classification, outcome tracking."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum


MAX_RETRIES: int = 3
SAME_FAILURE_THRESHOLD: int = 2


class StrictnessLevel(StrEnum):
    """Progressive retry strictness ladder."""

    GENTLE = "gentle"
    EXPLICIT = "explicit"
    FORCED = "forced"


STRICTNESS_ORDER: list[StrictnessLevel] = [
    StrictnessLevel.GENTLE,
    StrictnessLevel.EXPLICIT,
    StrictnessLevel.FORCED,
]


class FailureCategory(StrEnum):
    """Normalized retry-triggering failure kind."""

    SCHEMA_FAIL = "schema_fail"
    HARD_GATE_FAIL = "hard_gate_fail"
    PARTIAL_SCHEMA = "partial_schema"
    MIXED_VALIDATION_FAIL = "mixed_validation_fail"


class RetryOutcome(StrEnum):
    """Final disposition of the retry loop."""

    NOT_NEEDED = "not_needed"
    RECOVERED = "recovered"
    EXHAUSTED = "exhausted"


@dataclass(slots=True)
class RetryResult:
    """Retry loop metadata attached to ExecutionResult."""

    attempts: int = 1
    max_retries: int = MAX_RETRIES
    outcome: RetryOutcome = RetryOutcome.NOT_NEEDED
    final_strictness: StrictnessLevel | None = None
    failure_reasons: list[FailureCategory] = field(default_factory=list)
    same_failure_stopped: bool = False
