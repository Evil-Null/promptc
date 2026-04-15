"""Retry engine — failure classification, strictness escalation, prompt patching."""

from __future__ import annotations

from dataclasses import replace
from typing import TYPE_CHECKING

from interceptor.validation.retry_models import (
    FailureCategory,
    SAME_FAILURE_THRESHOLD,
    StrictnessLevel,
    STRICTNESS_ORDER,
)

if TYPE_CHECKING:
    from interceptor.compilation.models import CompiledPrompt
    from interceptor.validation.gate_models import GateEvaluation
    from interceptor.validation.models import ValidationResult

_STRICTNESS_SUFFIXES: dict[StrictnessLevel, str] = {
    StrictnessLevel.GENTLE: (
        "\n\nIMPORTANT: Please format your response exactly as requested. "
        "Follow the output schema and quality requirements precisely."
    ),
    StrictnessLevel.EXPLICIT: (
        "\n\nCRITICAL FORMAT REQUIREMENTS:\n"
        "1. Your response MUST match the requested output schema exactly.\n"
        "2. Include all required fields, sections, and structural elements.\n"
        "3. Cite specific references where quality gates require them.\n"
        "4. Do not omit any mandatory component."
    ),
    StrictnessLevel.FORCED: (
        "\n\nMANDATORY — FAILURE TO COMPLY WILL REJECT YOUR RESPONSE:\n"
        "- Output MUST be valid according to the requested format.\n"
        "- Every required field MUST be present and correctly typed.\n"
        "- Every hard quality gate MUST be satisfied.\n"
        "- Structural formatting MUST be exact.\n"
        "- If you previously failed, correct the specific issues now."
    ),
}


def classify_failure(
    validation: ValidationResult | None,
    gate_evaluation: GateEvaluation | None,
) -> FailureCategory | None:
    """Determine the retry-triggering failure kind, or None if no retry needed."""
    schema_failed = False
    partial_schema = False
    hard_gate_failed = False

    if validation is not None:
        status = getattr(validation, "status", None)
        if status is not None:
            status_val = str(status)
            if status_val == "fail":
                schema_failed = True
            elif status_val == "partial":
                partial_schema = True

    if gate_evaluation is not None:
        if not getattr(gate_evaluation, "hard_passed", True):
            hard_gate_failed = True

    if schema_failed and hard_gate_failed:
        return FailureCategory.MIXED_VALIDATION_FAIL
    if schema_failed:
        return FailureCategory.SCHEMA_FAIL
    if hard_gate_failed:
        return FailureCategory.HARD_GATE_FAIL
    if partial_schema:
        return FailureCategory.PARTIAL_SCHEMA
    return None


def build_retry_prompt(
    compiled_prompt: CompiledPrompt,
    strictness: StrictnessLevel,
) -> CompiledPrompt:
    """Return a copy of *compiled_prompt* with strictness suffix appended."""
    suffix = _STRICTNESS_SUFFIXES[strictness]
    return replace(compiled_prompt, compiled_text=compiled_prompt.compiled_text + suffix)


def should_stop_same_failure(
    failure_reasons: list[FailureCategory],
) -> bool:
    """Return True if the last failure has repeated >= SAME_FAILURE_THRESHOLD times."""
    if len(failure_reasons) < SAME_FAILURE_THRESHOLD:
        return False
    return (
        failure_reasons[-1] == failure_reasons[-2]
    )
