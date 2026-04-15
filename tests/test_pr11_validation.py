"""PR-11 tests — Output validation layer.

Classes A-J covering models, registry, each validator, service integration,
CLI display, and regression safety.  All deterministic, network-free.
"""

from __future__ import annotations

import json as json_mod
from dataclasses import dataclass

import pytest

from interceptor.validation.models import (
    PARTIAL_THRESHOLD,
    PASS_THRESHOLD,
    ValidationIssue,
    ValidationResult,
    ValidationStatus,
    status_from_score,
)
from interceptor.validation.registry import (
    get_validator,
    infer_format,
    validate_output,
)
from interceptor.validation.validators import (
    FreeformValidator,
    JsonValidator,
    MarkdownTableValidator,
    NumberedListValidator,
    SectionsValidator,
)


# ── A. Validation models & status thresholds ──────────────────────────────


class TestValidationModels:
    """A — model primitives and threshold math."""

    def test_status_pass_at_threshold(self) -> None:
        assert status_from_score(PASS_THRESHOLD) is ValidationStatus.PASS

    def test_status_pass_above(self) -> None:
        assert status_from_score(1.0) is ValidationStatus.PASS

    def test_status_partial_at_threshold(self) -> None:
        assert status_from_score(PARTIAL_THRESHOLD) is ValidationStatus.PARTIAL

    def test_status_partial_between(self) -> None:
        assert status_from_score(0.80) is ValidationStatus.PARTIAL

    def test_status_fail_below_partial(self) -> None:
        assert status_from_score(0.69) is ValidationStatus.FAIL

    def test_status_fail_zero(self) -> None:
        assert status_from_score(0.0) is ValidationStatus.FAIL

    def test_issue_creation(self) -> None:
        issue = ValidationIssue(rule="r1", message="boom")
        assert issue.rule == "r1"
        assert issue.message == "boom"

    def test_result_defaults(self) -> None:
        r = ValidationResult(
            status=ValidationStatus.PASS, score=1.0, validator_name="test"
        )
        assert r.issues == []

    def test_result_with_issues(self) -> None:
        issue = ValidationIssue(rule="x", message="y")
        r = ValidationResult(
            status=ValidationStatus.FAIL,
            score=0.0,
            validator_name="test",
            issues=[issue],
        )
        assert len(r.issues) == 1

    def test_status_enum_values(self) -> None:
        assert ValidationStatus.PASS == "pass"
        assert ValidationStatus.PARTIAL == "partial"
        assert ValidationStatus.FAIL == "fail"


# ── B. Validator registry & dispatch ──────────────────────────────────────


class TestValidatorRegistry:
    """B — registry lookup, convenience function, inference."""

    def test_get_json(self) -> None:
        assert isinstance(get_validator("json"), JsonValidator)

    def test_get_markdowntable(self) -> None:
        assert isinstance(get_validator("markdowntable"), MarkdownTableValidator)

    def test_get_sections(self) -> None:
        assert isinstance(get_validator("sections"), SectionsValidator)

    def test_get_numberedlist(self) -> None:
        assert isinstance(get_validator("numberedlist"), NumberedListValidator)

    def test_get_freeform(self) -> None:
        assert isinstance(get_validator("freeform"), FreeformValidator)

    def test_unknown_raises(self) -> None:
        with pytest.raises(ValueError, match="Unknown output format"):
            get_validator("xml")

    def test_validate_output_delegates(self) -> None:
        r = validate_output('{"a":1}', "json")
        assert r.status == "pass"

    def test_infer_json(self) -> None:
        assert infer_format("Return a JSON object") == "json"

    def test_infer_table(self) -> None:
        assert infer_format("Markdown table of results") == "markdowntable"

    def test_infer_sections(self) -> None:
        assert infer_format("Structured review with sections") == "sections"

    def test_infer_numbered(self) -> None:
        assert infer_format("Return a numbered list of steps") == "numberedlist"

    def test_infer_numbered_items(self) -> None:
        assert infer_format("Output numbered items") == "numberedlist"

    def test_infer_freeform_default(self) -> None:
        assert infer_format("Do whatever you want") == "freeform"

    def test_infer_empty(self) -> None:
        assert infer_format("") == "freeform"

    def test_infer_case_insensitive(self) -> None:
        assert infer_format("Return JSON data") == "json"


# ── C. JsonValidator ──────────────────────────────────────────────────────


class TestJsonValidator:
    """C — JSON format compliance."""

    def test_valid_object(self) -> None:
        r = JsonValidator().validate('{"key": "value"}', "")
        assert r.status == "pass"
        assert r.score == 1.0
        assert r.issues == []

    def test_valid_array(self) -> None:
        r = JsonValidator().validate("[1, 2, 3]", "")
        assert r.status == "pass"

    def test_invalid_json(self) -> None:
        r = JsonValidator().validate("{bad json", "")
        assert r.status == "fail"
        assert r.score == 0.5
        assert any(i.rule == "valid_json" for i in r.issues)

    def test_empty_input(self) -> None:
        r = JsonValidator().validate("", "")
        assert r.status == "fail"
        assert r.score == 0.0
        assert any(i.rule == "non_empty" for i in r.issues)

    def test_whitespace_only(self) -> None:
        r = JsonValidator().validate("   \n  ", "")
        assert r.status == "fail"

    def test_json_in_code_fence(self) -> None:
        text = '```json\n{"a": 1}\n```'
        r = JsonValidator().validate(text, "")
        assert r.status == "pass"

    def test_json_primitive_string(self) -> None:
        r = JsonValidator().validate('"hello"', "")
        assert r.status == "pass"

    def test_json_primitive_number(self) -> None:
        r = JsonValidator().validate("42", "")
        assert r.status == "pass"

    def test_nested_json(self) -> None:
        data = json_mod.dumps({"a": {"b": [1, 2]}})
        r = JsonValidator().validate(data, "")
        assert r.status == "pass"

    def test_validator_name(self) -> None:
        r = JsonValidator().validate("{}", "")
        assert r.validator_name == "json"


# ── D. MarkdownTableValidator ─────────────────────────────────────────────


class TestMarkdownTableValidator:
    """D — Markdown table format compliance."""

    VALID_TABLE = (
        "| Name | Age |\n"
        "| --- | --- |\n"
        "| Alice | 30 |\n"
        "| Bob | 25 |"
    )

    def test_valid_table(self) -> None:
        r = MarkdownTableValidator().validate(self.VALID_TABLE, "")
        assert r.status == "pass"
        assert r.score == 1.0

    def test_empty_input(self) -> None:
        r = MarkdownTableValidator().validate("", "")
        assert r.status == "fail"
        assert r.score == 0.0

    def test_no_table(self) -> None:
        r = MarkdownTableValidator().validate("Just plain text.", "")
        assert r.status == "fail"
        assert any(i.rule == "has_table" for i in r.issues)

    def test_pipes_without_separator(self) -> None:
        text = "| a | b |\n| c | d |"
        r = MarkdownTableValidator().validate(text, "")
        assert r.status == "fail"
        assert any(i.rule == "has_separator" for i in r.issues)

    def test_table_with_alignment(self) -> None:
        text = "| X | Y |\n| :---: | ---: |\n| 1 | 2 |"
        r = MarkdownTableValidator().validate(text, "")
        assert r.status == "pass"

    def test_validator_name(self) -> None:
        r = MarkdownTableValidator().validate(self.VALID_TABLE, "")
        assert r.validator_name == "markdowntable"


# ── E. SectionsValidator ──────────────────────────────────────────────────


class TestSectionsValidator:
    """E — Sections (heading-based) format compliance."""

    VALID_SECTIONS = (
        "## Summary\n\n"
        "This is a summary of the document content.\n\n"
        "## Details\n\n"
        "Here are the implementation details."
    )

    def test_valid_sections(self) -> None:
        r = SectionsValidator().validate(self.VALID_SECTIONS, "")
        assert r.status == "pass"
        assert r.score == 1.0

    def test_empty_input(self) -> None:
        r = SectionsValidator().validate("", "")
        assert r.status == "fail"

    def test_no_headings(self) -> None:
        text = "This is just a paragraph.\n" * 5
        r = SectionsValidator().validate(text, "")
        assert any(i.rule == "has_headings" for i in r.issues)

    def test_short_content_with_heading(self) -> None:
        r = SectionsValidator().validate("# Title\nShort.", "")
        assert any(i.rule == "min_length" for i in r.issues)

    def test_h1_heading_accepted(self) -> None:
        text = "# Main Title\n\n" + "Content here. " * 10
        r = SectionsValidator().validate(text, "")
        assert r.status == "pass"

    def test_h3_heading_accepted(self) -> None:
        text = "### Sub Section\n\n" + "Detailed content. " * 10
        r = SectionsValidator().validate(text, "")
        assert r.status == "pass"

    def test_validator_name(self) -> None:
        r = SectionsValidator().validate(self.VALID_SECTIONS, "")
        assert r.validator_name == "sections"


# ── F. NumberedListValidator ──────────────────────────────────────────────


class TestNumberedListValidator:
    """F — Numbered list format compliance."""

    def test_valid_list(self) -> None:
        text = "1. First item\n2. Second item\n3. Third item"
        r = NumberedListValidator().validate(text, "")
        assert r.status == "pass"

    def test_empty_input(self) -> None:
        r = NumberedListValidator().validate("", "")
        assert r.status == "fail"

    def test_no_items(self) -> None:
        r = NumberedListValidator().validate("Just text.", "")
        assert any(i.rule == "has_numbered_items" for i in r.issues)

    def test_parenthesis_numbering(self) -> None:
        text = "1) First\n2) Second"
        r = NumberedListValidator().validate(text, "")
        assert r.status == "pass"

    def test_indented_list(self) -> None:
        text = "  1. Indented first\n  2. Indented second"
        r = NumberedListValidator().validate(text, "")
        assert r.status == "pass"

    def test_validator_name(self) -> None:
        r = NumberedListValidator().validate("1. x", "")
        assert r.validator_name == "numberedlist"


# ── G. FreeformValidator ──────────────────────────────────────────────────


class TestFreeformValidator:
    """G — Freeform always passes."""

    def test_any_text(self) -> None:
        r = FreeformValidator().validate("Anything goes!", "")
        assert r.status == "pass"
        assert r.score == 1.0

    def test_empty_still_passes(self) -> None:
        r = FreeformValidator().validate("", "")
        assert r.status == "pass"

    def test_validator_name(self) -> None:
        r = FreeformValidator().validate("x", "")
        assert r.validator_name == "freeform"


# ── H. Service integration (buffered path) ───────────────────────────────


class TestServiceValidation:
    """H — AdapterService.execute_full() auto-validates when schema present."""

    @dataclass
    class _FakeCompiledPrompt:
        """Minimal stand-in with output_schema_text attribute."""

        compiled_text: str = "test prompt"
        raw_input: str = "test"
        template_name: str = "test"
        token_count_estimate: int = 10
        compression_level: str = "none"
        system_directive_text: str = ""
        chain_of_thought_text: str = ""
        output_schema_text: str = ""
        quality_gates_text: str = ""
        anti_patterns_text: str = ""
        user_input_text: str = ""

    def test_validation_runs_when_schema_present(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from interceptor.adapters.models import ExecutionResult
        from interceptor.adapters.service import AdapterService

        fake_result = ExecutionResult(backend="claude", text='{"ok": true}')

        def fake_send_full(self_adapter: object, request: object, *, client: object = None) -> ExecutionResult:
            return fake_result

        monkeypatch.setattr(
            "interceptor.adapters.claude.ClaudeAdapter.adapt",
            lambda self, **kw: type("R", (), {"backend": "claude", "payload": {}, "temperature": 0.7, "max_output_tokens": 4096, "streaming": False})(),
        )
        monkeypatch.setattr(
            "interceptor.adapters.claude.ClaudeAdapter.send_full",
            fake_send_full,
        )

        cp = self._FakeCompiledPrompt(output_schema_text="Return a JSON object")
        svc = AdapterService()
        result = svc.execute_full(
            backend="claude",
            compiled_prompt=cp,
            temperature=0.7,
            max_output_tokens=4096,
        )
        assert result.validation is not None
        assert result.validation.status == "pass"
        assert result.validation.validator_name == "json"

    def test_no_validation_when_schema_empty(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from interceptor.adapters.models import ExecutionResult
        from interceptor.adapters.service import AdapterService

        fake_result = ExecutionResult(backend="claude", text="hello")

        monkeypatch.setattr(
            "interceptor.adapters.claude.ClaudeAdapter.adapt",
            lambda self, **kw: type("R", (), {"backend": "claude", "payload": {}, "temperature": 0.7, "max_output_tokens": 4096, "streaming": False})(),
        )
        monkeypatch.setattr(
            "interceptor.adapters.claude.ClaudeAdapter.send_full",
            lambda self, req, **kw: fake_result,
        )

        cp = self._FakeCompiledPrompt(output_schema_text="")
        svc = AdapterService()
        result = svc.execute_full(
            backend="claude",
            compiled_prompt=cp,
            temperature=0.7,
            max_output_tokens=4096,
        )
        assert result.validation is None

    def test_no_validation_for_string_prompt(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from interceptor.adapters.models import ExecutionResult
        from interceptor.adapters.service import AdapterService

        fake_result = ExecutionResult(backend="gpt", text="response")

        monkeypatch.setattr(
            "interceptor.adapters.gpt.GptAdapter.adapt",
            lambda self, **kw: type("R", (), {"backend": "gpt", "payload": {}, "temperature": 0.7, "max_output_tokens": 4096, "streaming": False})(),
        )
        monkeypatch.setattr(
            "interceptor.adapters.gpt.GptAdapter.send_full",
            lambda self, req, **kw: fake_result,
        )

        svc = AdapterService()
        result = svc.execute_full(
            backend="gpt",
            compiled_prompt="plain string",
            temperature=0.7,
            max_output_tokens=4096,
        )
        assert result.validation is None

    def test_validation_fail_attached(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from interceptor.adapters.models import ExecutionResult
        from interceptor.adapters.service import AdapterService

        fake_result = ExecutionResult(backend="claude", text="not json at all")

        monkeypatch.setattr(
            "interceptor.adapters.claude.ClaudeAdapter.adapt",
            lambda self, **kw: type("R", (), {"backend": "claude", "payload": {}, "temperature": 0.7, "max_output_tokens": 4096, "streaming": False})(),
        )
        monkeypatch.setattr(
            "interceptor.adapters.claude.ClaudeAdapter.send_full",
            lambda self, req, **kw: fake_result,
        )

        cp = self._FakeCompiledPrompt(output_schema_text="Return a JSON object")
        svc = AdapterService()
        result = svc.execute_full(
            backend="claude",
            compiled_prompt=cp,
            temperature=0.7,
            max_output_tokens=4096,
        )
        assert result.validation is not None
        assert result.validation.status == "fail"


# ── I. CLI validation display ─────────────────────────────────────────────


class TestCliValidation:
    """I — _render_validation helper behaviour."""

    def test_render_fail_outputs_red(self, capsys: pytest.CaptureFixture[str]) -> None:
        from interceptor.cli import _render_validation
        from interceptor.validation.models import (
            ValidationIssue,
            ValidationResult,
            ValidationStatus,
        )

        vr = ValidationResult(
            status=ValidationStatus.FAIL,
            score=0.5,
            validator_name="json",
            issues=[ValidationIssue(rule="valid_json", message="Invalid JSON: Expecting value")],
        )
        _render_validation(vr)
        captured = capsys.readouterr().out
        assert "validation: fail" in captured
        assert "50%" in captured
        assert "Invalid JSON" in captured

    def test_render_partial_outputs_yellow(self, capsys: pytest.CaptureFixture[str]) -> None:
        from interceptor.cli import _render_validation
        from interceptor.validation.models import (
            ValidationIssue,
            ValidationResult,
            ValidationStatus,
        )

        vr = ValidationResult(
            status=ValidationStatus.PARTIAL,
            score=0.75,
            validator_name="sections",
            issues=[ValidationIssue(rule="min_length", message="Too short")],
        )
        _render_validation(vr)
        captured = capsys.readouterr().out
        assert "validation: partial" in captured
        assert "75%" in captured


# ── J. Regression safety ──────────────────────────────────────────────────


class TestRegressionSafety:
    """J — Ensure frozen PR-9/PR-10 contracts are intact."""

    def test_execution_result_has_validation_field(self) -> None:
        from interceptor.adapters.models import ExecutionResult

        r = ExecutionResult(backend="claude", text="hi")
        assert r.validation is None

    def test_execution_result_backward_compat(self) -> None:
        from interceptor.adapters.models import ExecutionResult

        r = ExecutionResult(
            backend="gpt",
            text="hello",
            finish_reason="stop",
            usage_input_tokens=10,
            usage_output_tokens=20,
        )
        assert r.text == "hello"
        assert r.validation is None

    def test_stream_event_unchanged(self) -> None:
        from interceptor.adapters.models import StreamEvent

        e = StreamEvent(type="content", text="hi", done=False)
        assert e.type == "content"
        assert not e.done

    def test_adapted_request_unchanged(self) -> None:
        from interceptor.adapters.models import AdaptedRequest

        r = AdaptedRequest(
            backend="claude",
            payload={"x": 1},
            temperature=0.7,
            max_output_tokens=100,
            streaming=False,
        )
        assert r.backend == "claude"
