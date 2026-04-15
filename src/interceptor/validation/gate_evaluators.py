"""Concrete gate evaluators — deterministic heuristic checkers."""

from __future__ import annotations

import re
from abc import ABC, abstractmethod

from interceptor.validation.gate_models import GateResult, GateSeverity

_WORD_NUMBERS: dict[str, int] = {
    "one": 1, "two": 2, "three": 3, "four": 4, "five": 5,
    "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10,
}


def _extract_number(text: str) -> int | None:
    """Extract the first numeric value from gate text (digit or word)."""
    m = re.search(r"\b(\d+)\b", text)
    if m:
        return int(m.group(1))
    lower = text.lower()
    for word, num in _WORD_NUMBERS.items():
        if re.search(rf"\b{word}\b", lower):
            return num
    return None


class BaseGateEvaluator(ABC):
    """Common interface for gate evaluators."""

    name: str

    @abstractmethod
    def evaluate(
        self, gate_text: str, severity: GateSeverity, output: str,
    ) -> GateResult:
        """Evaluate *output* against the requirement in *gate_text*."""


class QuantitativeEvaluator(BaseGateEvaluator):
    """Count-based checks: 'at least N items', 'exactly N things'."""

    name = "quantitative"

    def evaluate(
        self, gate_text: str, severity: GateSeverity, output: str,
    ) -> GateResult:
        n = _extract_number(gate_text)
        if n is None:
            return GateResult(
                gate_text=gate_text, severity=severity, passed=True,
                evaluator=self.name, detail="No numeric requirement extracted",
            )
        count = self._count_items(gate_text.lower(), output)
        passed = count >= n
        return GateResult(
            gate_text=gate_text, severity=severity, passed=passed,
            evaluator=self.name, detail=f"Found {count}, required >= {n}",
        )

    def _count_items(self, gate_lower: str, output: str) -> int:
        if "example" in gate_lower:
            return self._count_examples(output)
        if any(w in gate_lower for w in ("approach", "option", "alternative")):
            return self._count_sections(output)
        return self._count_sections(output)

    @staticmethod
    def _count_examples(output: str) -> int:
        code_blocks = len(re.findall(r"```", output)) // 2
        phrases = len(re.findall(
            r"\b(?:for example|e\.g\.|for instance|example:)",
            output, re.I,
        ))
        return code_blocks + phrases

    @staticmethod
    def _count_sections(output: str) -> int:
        return len(re.findall(r"^#{1,6}\s+\S", output, re.MULTILINE))


class CompletenessEvaluator(BaseGateEvaluator):
    """Structure completeness: 'every X must have Y'."""

    name = "completeness"

    def evaluate(
        self, gate_text: str, severity: GateSeverity, output: str,
    ) -> GateResult:
        lower = gate_text.lower()
        if "cite" in lower and ("line" in lower or "block" in lower):
            return self._check_line_citations(gate_text, severity, output)
        if "cwe" in lower or "owasp" in lower:
            return self._check_cwe_references(gate_text, severity, output)
        return GateResult(
            gate_text=gate_text, severity=severity, passed=True,
            evaluator=self.name,
            detail="No matching completeness check; assumed pass",
        )

    @staticmethod
    def _check_line_citations(
        gate_text: str, severity: GateSeverity, output: str,
    ) -> GateResult:
        refs = re.findall(r"(?:line\s+\d+|L\d+|:\d+)", output, re.I)
        passed = len(refs) > 0
        detail = (
            f"Found {len(refs)} line reference(s)"
            if passed else "No line references found"
        )
        return GateResult(
            gate_text=gate_text, severity=severity, passed=passed,
            evaluator="completeness", detail=detail,
        )

    @staticmethod
    def _check_cwe_references(
        gate_text: str, severity: GateSeverity, output: str,
    ) -> GateResult:
        refs = re.findall(r"(?:CWE-\d+|OWASP\s+\w+)", output, re.I)
        passed = len(refs) > 0
        detail = (
            f"Found {len(refs)} CWE/OWASP reference(s)"
            if passed else "No CWE/OWASP references found"
        )
        return GateResult(
            gate_text=gate_text, severity=severity, passed=passed,
            evaluator="completeness", detail=detail,
        )


# Keyword sets for semantic concept detection.
_CONCEPT_KEYWORDS: dict[str, list[str]] = {
    "failure mode": [
        "failure", "error", "fault", "crash", "timeout", "retry", "fallback",
    ],
    "component boundar": [
        "component", "service", "module", "boundary", "interface",
    ],
    "capacity estimate": [
        "capacity", "throughput", "requests per second", "rps", "load", "scale",
    ],
    "industry pattern": [
        "cqrs", "event sourcing", "saga", "pub/sub", "circuit breaker",
        "microservice",
    ],
    "flagged as critical": ["critical"],
    "proof-of-concept": ["proof", "poc", "exploit", "demonstration"],
    "dependency audit": ["dependency", "cve", "vulnerability", "package"],
    "complexity analysis": [
        "o(n)", "o(1)", "complexity", "big-o", "linear", "quadratic",
    ],
    "project convention": ["convention", "style guide", "standard", "consistent"],
    "avoid unnecessary jargon": [],
    "adapt language": [],
    "technically accurate": [],
}


class SemanticEvaluator(BaseGateEvaluator):
    """Heuristic presence/absence checks on output content."""

    name = "semantic"

    def evaluate(
        self, gate_text: str, severity: GateSeverity, output: str,
    ) -> GateResult:
        lower_gate = gate_text.lower()
        lower_output = output.lower()

        if "application" in lower_gate and "infrastructure" in lower_gate:
            has_app = "application" in lower_output
            has_infra = "infrastructure" in lower_output
            passed = has_app and has_infra
            return GateResult(
                gate_text=gate_text, severity=severity, passed=passed,
                evaluator=self.name,
                detail=(
                    f"application={'found' if has_app else 'missing'}, "
                    f"infrastructure={'found' if has_infra else 'missing'}"
                ),
            )

        for concept, keywords in _CONCEPT_KEYWORDS.items():
            if concept in lower_gate:
                if not keywords:
                    return GateResult(
                        gate_text=gate_text, severity=severity, passed=True,
                        evaluator=self.name,
                        detail="Cannot verify heuristically; assumed pass",
                    )
                found = [kw for kw in keywords if kw in lower_output]
                passed = len(found) > 0
                detail = (
                    f"Keywords found: {', '.join(found)}"
                    if passed else "Expected keywords not found in output"
                )
                return GateResult(
                    gate_text=gate_text, severity=severity, passed=passed,
                    evaluator=self.name, detail=detail,
                )

        return GateResult(
            gate_text=gate_text, severity=severity, passed=True,
            evaluator=self.name, detail="No matching heuristic; assumed pass",
        )
