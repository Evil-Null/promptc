"""Quality gate evaluation models — frozen value types."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum


class GateSeverity(StrEnum):
    """Gate importance level."""

    HARD = "hard"
    SOFT = "soft"


@dataclass(slots=True, frozen=True)
class GateResult:
    """Single gate evaluation outcome."""

    gate_text: str
    severity: GateSeverity
    passed: bool
    evaluator: str
    detail: str = ""


@dataclass(slots=True)
class GateEvaluation:
    """Aggregate quality gate evaluation result."""

    results: list[GateResult] = field(default_factory=list)

    @property
    def passed_hard_gates(self) -> int:
        return sum(
            1 for r in self.results
            if r.severity == GateSeverity.HARD and r.passed
        )

    @property
    def total_hard_gates(self) -> int:
        return sum(1 for r in self.results if r.severity == GateSeverity.HARD)

    @property
    def hard_passed(self) -> bool:
        return self.passed_hard_gates == self.total_hard_gates

    @property
    def gate_score(self) -> float:
        if self.total_hard_gates == 0:
            return 1.0
        return round(self.passed_hard_gates / self.total_hard_gates, 4)

    @property
    def warnings(self) -> list[GateResult]:
        return [
            r for r in self.results
            if r.severity == GateSeverity.SOFT and not r.passed
        ]

    @property
    def failures(self) -> list[GateResult]:
        return [
            r for r in self.results
            if r.severity == GateSeverity.HARD and not r.passed
        ]
