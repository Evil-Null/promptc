"""PR-12 tests — Quality gate evaluation layer.

Classes A-J covering gate models, classification, each evaluator family,
built-in template gate coverage, service integration, CLI display,
zero-hard-gate edge case, and regression safety.
"""

from __future__ import annotations

import json as json_mod
from dataclasses import dataclass

import pytest

from interceptor.validation.gate_evaluators import (
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
from interceptor.validation.gate_registry import classify_gate, evaluate_gates


# ── A. Gate models & score behavior ───────────────────────────────────────


class TestGateModels:
    """A — model primitives, properties, and score math."""

    def test_severity_values(self) -> None:
        assert GateSeverity.HARD == "hard"
        assert GateSeverity.SOFT == "soft"

    def test_gate_result_creation(self) -> None:
        r = GateResult(
            gate_text="test", severity=GateSeverity.HARD,
            passed=True, evaluator="q",
        )
        assert r.gate_text == "test"
        assert r.passed is True
        assert r.detail == ""

    def test_gate_result_with_detail(self) -> None:
        r = GateResult(
            gate_text="g", severity=GateSeverity.SOFT,
            passed=False, evaluator="s", detail="info",
        )
        assert r.detail == "info"

    def test_empty_evaluation_defaults(self) -> None:
        ev = GateEvaluation()
        assert ev.passed_hard_gates == 0
        assert ev.total_hard_gates == 0
        assert ev.hard_passed is True
        assert ev.gate_score == 1.0
        assert ev.warnings == []
        assert ev.failures == []

    def test_all_hard_pass(self) -> None:
        ev = GateEvaluation(results=[
            GateResult("a", GateSeverity.HARD, True, "q"),
            GateResult("b", GateSeverity.HARD, True, "q"),
        ])
        assert ev.hard_passed is True
        assert ev.gate_score == 1.0
        assert ev.failures == []

    def test_one_hard_fail(self) -> None:
        ev = GateEvaluation(results=[
            GateResult("a", GateSeverity.HARD, True, "q"),
            GateResult("b", GateSeverity.HARD, False, "q"),
        ])
        assert ev.hard_passed is False
        assert ev.gate_score == 0.5
        assert len(ev.failures) == 1

    def test_gate_score_rounding(self) -> None:
        ev = GateEvaluation(results=[
            GateResult("a", GateSeverity.HARD, True, "q"),
            GateResult("b", GateSeverity.HARD, True, "q"),
            GateResult("c", GateSeverity.HARD, False, "q"),
        ])
        assert ev.gate_score == 0.6667

    def test_soft_fail_is_warning(self) -> None:
        ev = GateEvaluation(results=[
            GateResult("a", GateSeverity.SOFT, False, "s", "warn"),
        ])
        assert ev.hard_passed is True
        assert len(ev.warnings) == 1
        assert ev.warnings[0].gate_text == "a"

    def test_mixed_hard_soft(self) -> None:
        ev = GateEvaluation(results=[
            GateResult("h1", GateSeverity.HARD, True, "q"),
            GateResult("h2", GateSeverity.HARD, False, "q"),
            GateResult("s1", GateSeverity.SOFT, False, "s"),
            GateResult("s2", GateSeverity.SOFT, True, "s"),
        ])
        assert ev.hard_passed is False
        assert ev.gate_score == 0.5
        assert len(ev.failures) == 1
        assert len(ev.warnings) == 1


# ── B. Gate classification ────────────────────────────────────────────────


class TestGateClassification:
    """B — classify_gate routing to evaluator families."""

    def test_digit_routes_quantitative(self) -> None:
        ev = classify_gate("At least 3 options")
        assert ev.name == "quantitative"

    def test_word_number_routes_quantitative(self) -> None:
        ev = classify_gate("Must include at least one concrete example")
        assert ev.name == "quantitative"

    def test_every_must_routes_completeness(self) -> None:
        ev = classify_gate("Every issue must cite a specific line or block")
        assert ev.name == "completeness"

    def test_general_routes_semantic(self) -> None:
        ev = classify_gate("Must address failure modes explicitly")
        assert ev.name == "semantic"

    def test_should_routes_semantic(self) -> None:
        ev = classify_gate("Should avoid unnecessary jargon")
        assert ev.name == "semantic"

    def test_empty_routes_semantic(self) -> None:
        ev = classify_gate("")
        assert ev.name == "semantic"

    def test_extract_number_digit(self) -> None:
        assert _extract_number("At least 3 options") == 3

    def test_extract_number_word(self) -> None:
        assert _extract_number("at least one example") == 1

    def test_extract_number_none(self) -> None:
        assert _extract_number("Must address failures") is None


# ── C. QuantitativeEvaluator ─────────────────────────────────────────────


class TestQuantitativeEvaluator:
    """C — count-based gate checks."""

    def test_example_present_passes(self) -> None:
        output = "Here is an example:\n```python\nprint('hi')\n```"
        r = QuantitativeEvaluator().evaluate(
            "Must include at least one concrete example",
            GateSeverity.HARD, output,
        )
        assert r.passed is True
        assert r.evaluator == "quantitative"

    def test_example_phrase_passes(self) -> None:
        output = "For example, you can use a dict."
        r = QuantitativeEvaluator().evaluate(
            "Must include at least one concrete example",
            GateSeverity.HARD, output,
        )
        assert r.passed is True

    def test_no_example_fails(self) -> None:
        output = "This is a plain explanation without examples."
        r = QuantitativeEvaluator().evaluate(
            "Must include at least one concrete example",
            GateSeverity.HARD, output,
        )
        assert r.passed is False

    def test_three_options_pass(self) -> None:
        output = "## Option A\nDetails\n## Option B\nDetails\n## Option C\nDetails"
        r = QuantitativeEvaluator().evaluate(
            "At least 3 options", GateSeverity.HARD, output,
        )
        assert r.passed is True

    def test_three_options_fail(self) -> None:
        output = "## Only one option\nDetails"
        r = QuantitativeEvaluator().evaluate(
            "At least 3 options", GateSeverity.HARD, output,
        )
        assert r.passed is False

    def test_no_number_passes(self) -> None:
        r = QuantitativeEvaluator().evaluate(
            "No number here", GateSeverity.HARD, "anything",
        )
        assert r.passed is True
        assert "No numeric requirement" in r.detail

    def test_eg_counts(self) -> None:
        output = "e.g. use a list. For instance, arrays work."
        r = QuantitativeEvaluator().evaluate(
            "At least two examples", GateSeverity.HARD, output,
        )
        assert r.passed is True

    def test_empty_output_fails(self) -> None:
        r = QuantitativeEvaluator().evaluate(
            "Must include at least one concrete example",
            GateSeverity.HARD, "",
        )
        assert r.passed is False


# ── D. CompletenessEvaluator ─────────────────────────────────────────────


class TestCompletenessEvaluator:
    """D — structure completeness checks."""

    def test_line_citation_present(self) -> None:
        output = "Bug on line 42: missing null check"
        r = CompletenessEvaluator().evaluate(
            "Every issue must cite a specific line or block",
            GateSeverity.HARD, output,
        )
        assert r.passed is True
        assert "1 line reference" in r.detail

    def test_line_citation_missing(self) -> None:
        output = "There is a bug somewhere in the code."
        r = CompletenessEvaluator().evaluate(
            "Every issue must cite a specific line or block",
            GateSeverity.HARD, output,
        )
        assert r.passed is False

    def test_cwe_reference_present(self) -> None:
        output = "SQL injection found (CWE-89). Also OWASP A03."
        r = CompletenessEvaluator().evaluate(
            "Every finding must reference a specific CWE or OWASP category",
            GateSeverity.HARD, output,
        )
        assert r.passed is True
        assert "2 CWE/OWASP" in r.detail

    def test_cwe_reference_missing(self) -> None:
        output = "Found a security issue with the login form."
        r = CompletenessEvaluator().evaluate(
            "Every finding must reference a specific CWE or OWASP category",
            GateSeverity.HARD, output,
        )
        assert r.passed is False

    def test_unknown_pattern_passes(self) -> None:
        r = CompletenessEvaluator().evaluate(
            "Every module must be documented",
            GateSeverity.HARD, "some output",
        )
        assert r.passed is True
        assert "assumed pass" in r.detail

    def test_L_notation_detected(self) -> None:
        output = "Issue at L15 and L30"
        r = CompletenessEvaluator().evaluate(
            "Every issue must cite a specific line or block",
            GateSeverity.HARD, output,
        )
        assert r.passed is True

    def test_colon_line_detected(self) -> None:
        output = "file.py:42 has an error"
        r = CompletenessEvaluator().evaluate(
            "Every issue must cite a specific line or block",
            GateSeverity.HARD, output,
        )
        assert r.passed is True


# ── E. SemanticEvaluator ─────────────────────────────────────────────────


class TestSemanticEvaluator:
    """E — heuristic keyword checks."""

    def test_failure_modes_present(self) -> None:
        output = "The system handles failure by retrying with exponential backoff."
        r = SemanticEvaluator().evaluate(
            "Must address failure modes explicitly",
            GateSeverity.HARD, output,
        )
        assert r.passed is True

    def test_failure_modes_missing(self) -> None:
        output = "The system processes requests quickly."
        r = SemanticEvaluator().evaluate(
            "Must address failure modes explicitly",
            GateSeverity.HARD, output,
        )
        assert r.passed is False

    def test_component_boundaries_present(self) -> None:
        output = "The auth service communicates with the user module via API."
        r = SemanticEvaluator().evaluate(
            "Must define clear component boundaries",
            GateSeverity.HARD, output,
        )
        assert r.passed is True

    def test_flagged_critical_present(self) -> None:
        output = "This is a critical vulnerability that must be fixed."
        r = SemanticEvaluator().evaluate(
            "Security vulnerabilities must be flagged as critical",
            GateSeverity.HARD, output,
        )
        assert r.passed is True

    def test_flagged_critical_missing(self) -> None:
        output = "Found a minor issue."
        r = SemanticEvaluator().evaluate(
            "Security vulnerabilities must be flagged as critical",
            GateSeverity.HARD, output,
        )
        assert r.passed is False

    def test_technically_accurate_assumed_pass(self) -> None:
        r = SemanticEvaluator().evaluate(
            "Explanation must be technically accurate",
            GateSeverity.HARD, "any output",
        )
        assert r.passed is True
        assert "assumed pass" in r.detail

    def test_avoid_jargon_assumed_pass(self) -> None:
        r = SemanticEvaluator().evaluate(
            "Should avoid unnecessary jargon",
            GateSeverity.SOFT, "any output",
        )
        assert r.passed is True

    def test_app_and_infra_both_present(self) -> None:
        output = "We audit application code and infrastructure configs."
        r = SemanticEvaluator().evaluate(
            "Should assess both application and infrastructure security",
            GateSeverity.SOFT, output,
        )
        assert r.passed is True

    def test_app_and_infra_one_missing(self) -> None:
        output = "We only check the application layer."
        r = SemanticEvaluator().evaluate(
            "Should assess both application and infrastructure security",
            GateSeverity.SOFT, output,
        )
        assert r.passed is False
        assert "infrastructure=missing" in r.detail

    def test_industry_patterns_present(self) -> None:
        output = "Consider CQRS for read-heavy workloads and saga for transactions."
        r = SemanticEvaluator().evaluate(
            "Should reference industry patterns (CQRS, event sourcing, etc.)",
            GateSeverity.SOFT, output,
        )
        assert r.passed is True

    def test_unknown_gate_assumed_pass(self) -> None:
        r = SemanticEvaluator().evaluate(
            "Must be written in iambic pentameter",
            GateSeverity.HARD, "any output",
        )
        assert r.passed is True
        assert "No matching heuristic" in r.detail

    def test_dependency_audit_present(self) -> None:
        output = "Dependency scan found CVE-2024-1234 in package X."
        r = SemanticEvaluator().evaluate(
            "Should include dependency audit results",
            GateSeverity.SOFT, output,
        )
        assert r.passed is True


# ── F. Built-in template gate coverage ───────────────────────────────────


class TestBuiltinTemplateGates:
    """F — evaluate real built-in template gates against sample outputs."""

    GOOD_CODE_REVIEW = (
        "## Summary\n\nThe code has two issues.\n\n"
        "## Issues\n\n"
        "1. **Critical** — SQL injection on line 42\n"
        "2. **High** — Missing null check at line 87\n\n"
        "## Recommendations\n\nFix the critical vulnerability first."
    )

    GOOD_SECURITY_AUDIT = (
        "## Executive Summary\n\nTwo vulnerabilities found.\n\n"
        "## Findings\n\n"
        "1. SQL Injection (CWE-89, critical) — line 42 allows unsanitized input. "
        "PoC: `curl -d 'id=1 OR 1=1' /api/user`. Proof of concept shows full bypass.\n\n"
        "2. XSS (CWE-79, OWASP A03) — reflected input on line 15.\n\n"
        "## Action Plan\n\nPrioritize the SQL injection fix."
    )

    GOOD_ARCHITECTURE = (
        "## Components\n\n"
        "The API service handles requests. The auth module manages tokens.\n\n"
        "## Failure Modes\n\n"
        "On timeout, the circuit breaker triggers retry with fallback.\n\n"
        "## Trade-offs\n\nMonolith vs microservice boundary considered."
    )

    GOOD_EXPLAIN = (
        "## Summary\n\nA closure captures variables from its scope.\n\n"
        "## Explanation\n\n"
        "For example, in Python:\n```python\ndef make_adder(n):\n"
        "    return lambda x: x + n\n```\n"
        "This is technically sound because the inner function retains "
        "a reference to `n` in its closure."
    )

    def test_code_review_gates(self) -> None:
        ev = evaluate_gates(
            hard_gates=[
                "Every issue must cite a specific line or block",
                "Security vulnerabilities must be flagged as critical",
            ],
            soft_gates=[
                "Style suggestions should reference project conventions",
                "Performance notes should include complexity analysis",
            ],
            output=self.GOOD_CODE_REVIEW,
        )
        assert ev.hard_passed is True

    def test_security_audit_gates(self) -> None:
        ev = evaluate_gates(
            hard_gates=[
                "Every finding must reference a specific CWE or OWASP category",
                "Critical findings must include proof-of-concept or clear exploit path",
            ],
            soft_gates=[
                "Should assess both application and infrastructure security",
                "Should include dependency audit results",
            ],
            output=self.GOOD_SECURITY_AUDIT,
        )
        assert ev.hard_passed is True

    def test_architecture_gates(self) -> None:
        ev = evaluate_gates(
            hard_gates=[
                "Must address failure modes explicitly",
                "Must define clear component boundaries",
            ],
            soft_gates=[
                "Should include capacity estimates",
                "Should reference industry patterns (CQRS, event sourcing, etc.)",
            ],
            output=self.GOOD_ARCHITECTURE,
        )
        assert ev.hard_passed is True

    def test_explain_gates(self) -> None:
        ev = evaluate_gates(
            hard_gates=[
                "Explanation must be technically accurate",
                "Must include at least one concrete example",
            ],
            soft_gates=[
                "Should adapt language to apparent skill level",
                "Should avoid unnecessary jargon",
            ],
            output=self.GOOD_EXPLAIN,
        )
        assert ev.hard_passed is True

    def test_bad_output_fails_hard_gates(self) -> None:
        ev = evaluate_gates(
            hard_gates=[
                "Every issue must cite a specific line or block",
                "Security vulnerabilities must be flagged as critical",
            ],
            soft_gates=[],
            output="The code looks fine. No issues found.",
        )
        assert ev.hard_passed is False
        assert len(ev.failures) >= 1


# ── G. Service integration (buffered path) ───────────────────────────────


class TestServiceGateIntegration:
    """G — AdapterService.execute_full() auto-evaluates gates."""

    @dataclass
    class _FakeCompiledPrompt:
        compiled_text: str = "test"
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
        quality_gates_hard: list[str] | None = None
        quality_gates_soft: list[str] | None = None

        def __post_init__(self) -> None:
            if self.quality_gates_hard is None:
                self.quality_gates_hard = []
            if self.quality_gates_soft is None:
                self.quality_gates_soft = []

    def test_gates_run_when_present(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from interceptor.adapters.models import ExecutionResult
        from interceptor.adapters.service import AdapterService

        output = "## Summary\nBug on line 42. Critical vulnerability."
        fake_result = ExecutionResult(backend="claude", text=output)

        monkeypatch.setattr(
            "interceptor.adapters.claude.ClaudeAdapter.adapt",
            lambda self, **kw: type("R", (), {
                "backend": "claude", "payload": {}, "temperature": 0.7,
                "max_output_tokens": 4096, "streaming": False,
            })(),
        )
        monkeypatch.setattr(
            "interceptor.adapters.claude.ClaudeAdapter.send_full",
            lambda self, req, **kw: fake_result,
        )

        cp = self._FakeCompiledPrompt(
            quality_gates_hard=["Every issue must cite a specific line or block"],
            quality_gates_soft=["Should reference project conventions"],
        )
        svc = AdapterService()
        result = svc.execute_full(
            backend="claude", compiled_prompt=cp,
            temperature=0.7, max_output_tokens=4096,
        )
        assert result.gate_evaluation is not None
        assert result.gate_evaluation.hard_passed is True

    def test_no_gates_when_empty(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from interceptor.adapters.models import ExecutionResult
        from interceptor.adapters.service import AdapterService

        fake_result = ExecutionResult(backend="claude", text="hello")

        monkeypatch.setattr(
            "interceptor.adapters.claude.ClaudeAdapter.adapt",
            lambda self, **kw: type("R", (), {
                "backend": "claude", "payload": {}, "temperature": 0.7,
                "max_output_tokens": 4096, "streaming": False,
            })(),
        )
        monkeypatch.setattr(
            "interceptor.adapters.claude.ClaudeAdapter.send_full",
            lambda self, req, **kw: fake_result,
        )

        cp = self._FakeCompiledPrompt()
        svc = AdapterService()
        result = svc.execute_full(
            backend="claude", compiled_prompt=cp,
            temperature=0.7, max_output_tokens=4096,
        )
        assert result.gate_evaluation is None

    def test_no_gates_for_string_prompt(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from interceptor.adapters.models import ExecutionResult
        from interceptor.adapters.service import AdapterService

        fake_result = ExecutionResult(backend="gpt", text="response")

        monkeypatch.setattr(
            "interceptor.adapters.gpt.GptAdapter.adapt",
            lambda self, **kw: type("R", (), {
                "backend": "gpt", "payload": {}, "temperature": 0.7,
                "max_output_tokens": 4096, "streaming": False,
            })(),
        )
        monkeypatch.setattr(
            "interceptor.adapters.gpt.GptAdapter.send_full",
            lambda self, req, **kw: fake_result,
        )

        svc = AdapterService()
        result = svc.execute_full(
            backend="gpt", compiled_prompt="plain string",
            temperature=0.7, max_output_tokens=4096,
        )
        assert result.gate_evaluation is None

    def test_hard_failure_attached(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from interceptor.adapters.models import ExecutionResult
        from interceptor.adapters.service import AdapterService

        fake_result = ExecutionResult(backend="claude", text="No lines referenced.")

        monkeypatch.setattr(
            "interceptor.adapters.claude.ClaudeAdapter.adapt",
            lambda self, **kw: type("R", (), {
                "backend": "claude", "payload": {}, "temperature": 0.7,
                "max_output_tokens": 4096, "streaming": False,
            })(),
        )
        monkeypatch.setattr(
            "interceptor.adapters.claude.ClaudeAdapter.send_full",
            lambda self, req, **kw: fake_result,
        )

        cp = self._FakeCompiledPrompt(
            quality_gates_hard=["Every issue must cite a specific line or block"],
        )
        svc = AdapterService()
        result = svc.execute_full(
            backend="claude", compiled_prompt=cp,
            temperature=0.7, max_output_tokens=4096,
        )
        assert result.gate_evaluation is not None
        assert result.gate_evaluation.hard_passed is False


# ── H. CLI gate display ──────────────────────────────────────────────────


class TestCliGateDisplay:
    """H — _render_gate_evaluation helper and JSON output."""

    def test_render_hard_failure(self, capsys: pytest.CaptureFixture[str]) -> None:
        from interceptor.cli import _render_gate_evaluation

        ev = GateEvaluation(results=[
            GateResult("Must cite lines", GateSeverity.HARD, False, "completeness", "No refs"),
        ])
        _render_gate_evaluation(ev)
        captured = capsys.readouterr().out
        assert "FAIL" in captured
        assert "Must cite lines" in captured
        assert "No refs" in captured

    def test_render_soft_warning(self, capsys: pytest.CaptureFixture[str]) -> None:
        from interceptor.cli import _render_gate_evaluation

        ev = GateEvaluation(results=[
            GateResult("Should include X", GateSeverity.SOFT, False, "semantic", "missing"),
        ])
        _render_gate_evaluation(ev)
        captured = capsys.readouterr().out
        assert "warning" in captured
        assert "Should include X" in captured

    def test_render_mixed(self, capsys: pytest.CaptureFixture[str]) -> None:
        from interceptor.cli import _render_gate_evaluation

        ev = GateEvaluation(results=[
            GateResult("hard gate", GateSeverity.HARD, False, "q", "detail"),
            GateResult("soft gate", GateSeverity.SOFT, False, "s", "warn"),
        ])
        _render_gate_evaluation(ev)
        captured = capsys.readouterr().out
        assert "FAIL" in captured
        assert "warning" in captured

    def test_all_pass_silent(self) -> None:
        ev = GateEvaluation(results=[
            GateResult("gate", GateSeverity.HARD, True, "q"),
        ])
        assert ev.hard_passed is True
        assert ev.warnings == []


# ── I. Zero-hard-gate behavior ───────────────────────────────────────────


class TestZeroHardGates:
    """I — edge case: only soft gates or no gates at all."""

    def test_only_soft_gates(self) -> None:
        ev = evaluate_gates(
            hard_gates=[],
            soft_gates=["Should include examples"],
            output="No examples here.",
        )
        assert ev.hard_passed is True
        assert ev.gate_score == 1.0
        assert ev.total_hard_gates == 0

    def test_only_soft_with_warnings(self) -> None:
        ev = evaluate_gates(
            hard_gates=[],
            soft_gates=["Must address failure modes explicitly"],
            output="Everything is great.",
        )
        assert ev.hard_passed is True
        assert len(ev.warnings) == 1

    def test_empty_gates(self) -> None:
        ev = evaluate_gates(hard_gates=[], soft_gates=[], output="anything")
        assert ev.hard_passed is True
        assert ev.gate_score == 1.0
        assert ev.results == []


# ── J. Regression safety ─────────────────────────────────────────────────


class TestRegressionSafety:
    """J — PR-9/PR-10/PR-11 contracts intact."""

    def test_execution_result_has_gate_evaluation_field(self) -> None:
        from interceptor.adapters.models import ExecutionResult

        r = ExecutionResult(backend="claude", text="hi")
        assert r.gate_evaluation is None

    def test_execution_result_backward_compat(self) -> None:
        from interceptor.adapters.models import ExecutionResult

        r = ExecutionResult(
            backend="gpt", text="hello", finish_reason="stop",
            usage_input_tokens=10, usage_output_tokens=20,
        )
        assert r.text == "hello"
        assert r.validation is None
        assert r.gate_evaluation is None

    def test_stream_event_unchanged(self) -> None:
        from interceptor.adapters.models import StreamEvent

        e = StreamEvent(type="content", text="hi", done=False)
        assert e.type == "content"

    def test_compiled_prompt_has_gate_lists(self) -> None:
        from interceptor.compilation.models import CompiledPrompt

        cp = CompiledPrompt(
            template_name="t", raw_input="x", compiled_text="y",
            token_count_estimate=5, compression_level="none",
        )
        assert cp.quality_gates_hard == []
        assert cp.quality_gates_soft == []

    def test_compiled_prompt_gate_lists_populated(self) -> None:
        from interceptor.compilation.models import CompiledPrompt

        cp = CompiledPrompt(
            template_name="t", raw_input="x", compiled_text="y",
            token_count_estimate=5, compression_level="none",
            quality_gates_hard=["gate1"],
            quality_gates_soft=["gate2"],
        )
        assert cp.quality_gates_hard == ["gate1"]
        assert cp.quality_gates_soft == ["gate2"]

    def test_pr11_validation_still_works(self) -> None:
        from interceptor.validation.registry import validate_output

        r = validate_output('{"a": 1}', "json")
        assert r.status == "pass"
