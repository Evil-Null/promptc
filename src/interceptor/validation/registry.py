"""Validator registry — dispatch by format string + inference helper."""

from __future__ import annotations

from interceptor.validation.models import ValidationResult
from interceptor.validation.validators import (
    BaseValidator,
    FreeformValidator,
    JsonValidator,
    MarkdownTableValidator,
    NumberedListValidator,
    SectionsValidator,
)

_VALIDATORS: dict[str, BaseValidator] = {
    "json": JsonValidator(),
    "markdowntable": MarkdownTableValidator(),
    "sections": SectionsValidator(),
    "numberedlist": NumberedListValidator(),
    "freeform": FreeformValidator(),
}


def get_validator(output_format: str) -> BaseValidator:
    """Look up validator by format name. Raises ValueError on unknown."""
    validator = _VALIDATORS.get(output_format)
    if validator is None:
        raise ValueError(f"Unknown output format: {output_format!r}")
    return validator


def validate_output(
    text: str,
    output_format: str,
    output_schema: str = "",
) -> ValidationResult:
    """One-shot convenience: resolve validator then validate *text*."""
    return get_validator(output_format).validate(text, output_schema)


def infer_format(output_schema: str) -> str:
    """Heuristically derive format from output_schema description text.

    Returns one of the five canonical format names.  The detection uses
    simple keyword matching — intentionally boring and deterministic.
    """
    lower = output_schema.lower()
    if "json" in lower:
        return "json"
    if "table" in lower:
        return "markdowntable"
    if "numbered list" in lower or "numbered items" in lower:
        return "numberedlist"
    if "section" in lower:
        return "sections"
    return "freeform"
