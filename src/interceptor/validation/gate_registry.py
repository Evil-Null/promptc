"""Gate evaluator dispatch — classify gate text and evaluate."""

from __future__ import annotations

from interceptor.validation.gate_evaluators import (
    BaseGateEvaluator,
    CompletenessEvaluator,
    QuantitativeEvaluator,
    SemanticEvaluator,
    _extract_number,
)
from interceptor.validation.gate_models import (
    GateEvaluation,
    GateResult,
    GateSeverity,
)

_QUANTITATIVE = QuantitativeEvaluator()
_COMPLETENESS = CompletenessEvaluator()
_SEMANTIC = SemanticEvaluator()


def classify_gate(gate_text: str) -> BaseGateEvaluator:
    """Route gate text to the appropriate evaluator family."""
    lower = gate_text.lower()
    if _extract_number(gate_text) is not None:
        return _QUANTITATIVE
    if lower.startswith("every ") and "must" in lower:
        return _COMPLETENESS
    return _SEMANTIC


def evaluate_gates(
    *,
    hard_gates: list[str],
    soft_gates: list[str],
    output: str,
) -> GateEvaluation:
    """Evaluate all gates against *output* and return aggregate result."""
    results: list[GateResult] = []
    for gate_text in hard_gates:
        evaluator = classify_gate(gate_text)
        results.append(evaluator.evaluate(gate_text, GateSeverity.HARD, output))
    for gate_text in soft_gates:
        evaluator = classify_gate(gate_text)
        results.append(evaluator.evaluate(gate_text, GateSeverity.SOFT, output))
    return GateEvaluation(results=results)
