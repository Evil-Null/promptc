"""Concrete validators for each supported output schema format."""

from __future__ import annotations

import json as json_mod
import re
from abc import ABC, abstractmethod

from interceptor.validation.models import (
    ValidationIssue,
    ValidationResult,
    ValidationStatus,
    status_from_score,
)


class BaseValidator(ABC):
    """Common scoring logic shared by all format validators."""

    name: str

    @abstractmethod
    def validate(self, text: str, output_schema: str) -> ValidationResult:
        """Check *text* against the expected schema; return a scored result."""

    def _build_result(
        self,
        issues: list[ValidationIssue],
        total_rules: int,
    ) -> ValidationResult:
        passed = total_rules - len(issues)
        score = passed / total_rules if total_rules > 0 else 1.0
        return ValidationResult(
            status=status_from_score(score),
            score=round(score, 4),
            validator_name=self.name,
            issues=issues,
        )


class JsonValidator(BaseValidator):
    """Verify response is syntactically valid JSON."""

    name = "json"

    def validate(self, text: str, output_schema: str) -> ValidationResult:
        issues: list[ValidationIssue] = []
        stripped = text.strip()

        if not stripped:
            issues.append(ValidationIssue("non_empty", "Output is empty"))
            return ValidationResult(
                status=ValidationStatus.FAIL,
                score=0.0,
                validator_name=self.name,
                issues=issues,
            )

        clean = _strip_code_fence(stripped)
        try:
            json_mod.loads(clean)
        except json_mod.JSONDecodeError as exc:
            issues.append(
                ValidationIssue("valid_json", f"Invalid JSON: {exc.msg}")
            )

        return self._build_result(issues, 2)


class MarkdownTableValidator(BaseValidator):
    """Verify response contains a well-formed Markdown table."""

    name = "markdowntable"

    def validate(self, text: str, output_schema: str) -> ValidationResult:
        issues: list[ValidationIssue] = []
        stripped = text.strip()

        if not stripped:
            issues.append(ValidationIssue("non_empty", "Output is empty"))
            return ValidationResult(
                status=ValidationStatus.FAIL,
                score=0.0,
                validator_name=self.name,
                issues=issues,
            )

        lines = stripped.splitlines()
        has_pipe = any("|" in line for line in lines)
        has_separator = any(
            re.match(r"^\s*\|?[\s\-:|]+\|", line) for line in lines
        )

        if not has_pipe:
            issues.append(
                ValidationIssue("has_table", "No pipe-delimited table found")
            )
        if not has_separator:
            issues.append(
                ValidationIssue(
                    "has_separator", "No table separator row (---) found"
                )
            )

        return self._build_result(issues, 3)


class SectionsValidator(BaseValidator):
    """Verify response has Markdown heading structure."""

    name = "sections"

    def validate(self, text: str, output_schema: str) -> ValidationResult:
        issues: list[ValidationIssue] = []
        stripped = text.strip()

        if not stripped:
            issues.append(ValidationIssue("non_empty", "Output is empty"))
            return ValidationResult(
                status=ValidationStatus.FAIL,
                score=0.0,
                validator_name=self.name,
                issues=issues,
            )

        has_heading = bool(
            re.search(r"^#{1,6}\s+\S", stripped, re.MULTILINE)
        )
        if not has_heading:
            issues.append(
                ValidationIssue("has_headings", "No markdown headings found")
            )

        if len(stripped) < 50:
            issues.append(
                ValidationIssue(
                    "min_length", "Response shorter than 50 characters"
                )
            )

        return self._build_result(issues, 3)


class NumberedListValidator(BaseValidator):
    """Verify response contains a numbered list."""

    name = "numberedlist"

    def validate(self, text: str, output_schema: str) -> ValidationResult:
        issues: list[ValidationIssue] = []
        stripped = text.strip()

        if not stripped:
            issues.append(ValidationIssue("non_empty", "Output is empty"))
            return ValidationResult(
                status=ValidationStatus.FAIL,
                score=0.0,
                validator_name=self.name,
                issues=issues,
            )

        numbered = re.findall(
            r"^\s*\d+[.)]\s+\S", stripped, re.MULTILINE
        )
        if not numbered:
            issues.append(
                ValidationIssue(
                    "has_numbered_items", "No numbered list items found"
                )
            )

        return self._build_result(issues, 2)


class FreeformValidator(BaseValidator):
    """Accept any non-empty response. Always passes."""

    name = "freeform"

    def validate(self, text: str, output_schema: str) -> ValidationResult:
        return ValidationResult(
            status="pass",
            score=1.0,
            validator_name=self.name,
        )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_CODE_FENCE_RE = re.compile(
    r"^```\w*\s*\n(.*)\n```\s*$", re.DOTALL
)


def _strip_code_fence(text: str) -> str:
    """Remove surrounding fenced code block if present."""
    match = _CODE_FENCE_RE.match(text)
    return match.group(1).strip() if match else text
