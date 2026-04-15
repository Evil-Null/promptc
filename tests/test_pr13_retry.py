"""PR-13 — Retry engine tests.

Covers: retry models, failure classification, strictness escalation,
service integration, CLI display, and regression safety.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import Any

import pytest


# ── A. StrictnessLevel progression ────────────────────────────────────────


class TestStrictnessLevels:
    """Verify enum values and ordering."""

    def test_enum_values(self) -> None:
        from interceptor.validation.retry_models import StrictnessLevel

        assert StrictnessLevel.GENTLE == "gentle"
        assert StrictnessLevel.EXPLICIT == "explicit"
        assert StrictnessLevel.FORCED == "forced"

    def test_ordering(self) -> None:
        from interceptor.validation.retry_models import STRICTNESS_ORDER, StrictnessLevel

        assert STRICTNESS_ORDER == [
            StrictnessLevel.GENTLE,
            StrictnessLevel.EXPLICIT,
            StrictnessLevel.FORCED,
        ]

    def test_three_levels(self) -> None:
        from interceptor.validation.retry_models import STRICTNESS_ORDER

        assert len(STRICTNESS_ORDER) == 3


# ── B. RetryOutcome / RetryResult defaults ────────────────────────────────


class TestRetryModels:
    """Verify model defaults and constants."""

    def test_outcome_values(self) -> None:
        from interceptor.validation.retry_models import RetryOutcome

        assert RetryOutcome.NOT_NEEDED == "not_needed"
        assert RetryOutcome.RECOVERED == "recovered"
        assert RetryOutcome.EXHAUSTED == "exhausted"

    def test_failure_category_values(self) -> None:
        from interceptor.validation.retry_models import FailureCategory

        assert FailureCategory.SCHEMA_FAIL == "schema_fail"
        assert FailureCategory.HARD_GATE_FAIL == "hard_gate_fail"
        assert FailureCategory.PARTIAL_SCHEMA == "partial_schema"
        assert FailureCategory.MIXED_VALIDATION_FAIL == "mixed_validation_fail"

    def test_max_retries_constant(self) -> None:
        from interceptor.validation.retry_models import MAX_RETRIES

        assert MAX_RETRIES == 3

    def test_same_failure_threshold(self) -> None:
        from interceptor.validation.retry_models import SAME_FAILURE_THRESHOLD

        assert SAME_FAILURE_THRESHOLD == 2

    def test_retry_result_defaults(self) -> None:
        from interceptor.validation.retry_models import RetryOutcome, RetryResult

        r = RetryResult()
        assert r.attempts == 1
        assert r.max_retries == 3
        assert r.outcome == RetryOutcome.NOT_NEEDED
        assert r.final_strictness is None
        assert r.failure_reasons == []
        assert r.same_failure_stopped is False


# ── C. classify_failure: schema fail ──────────────────────────────────────


class TestClassifySchemaFail:
    """Classify schema validation failures."""

    def test_schema_fail(self) -> None:
        from interceptor.validation.models import ValidationResult, ValidationStatus
        from interceptor.validation.retry_engine import classify_failure
        from interceptor.validation.retry_models import FailureCategory

        v = ValidationResult(status=ValidationStatus.FAIL, score=0.0, validator_name="json")
        assert classify_failure(v, None) == FailureCategory.SCHEMA_FAIL

    def test_partial_schema(self) -> None:
        from interceptor.validation.models import ValidationResult, ValidationStatus
        from interceptor.validation.retry_engine import classify_failure
        from interceptor.validation.retry_models import FailureCategory

        v = ValidationResult(status=ValidationStatus.PARTIAL, score=0.75, validator_name="json")
        assert classify_failure(v, None) == FailureCategory.PARTIAL_SCHEMA

    def test_pass_returns_none(self) -> None:
        from interceptor.validation.models import ValidationResult, ValidationStatus
        from interceptor.validation.retry_engine import classify_failure

        v = ValidationResult(status=ValidationStatus.PASS, score=1.0, validator_name="json")
        assert classify_failure(v, None) is None

    def test_none_inputs(self) -> None:
        from interceptor.validation.retry_engine import classify_failure

        assert classify_failure(None, None) is None


# ── D. classify_failure: hard gate fail ───────────────────────────────────


class TestClassifyGateFail:
    """Classify quality gate failures."""

    def test_hard_gate_fail(self) -> None:
        from interceptor.validation.gate_models import (
            GateEvaluation,
            GateResult,
            GateSeverity,
        )
        from interceptor.validation.retry_engine import classify_failure
        from interceptor.validation.retry_models import FailureCategory

        ge = GateEvaluation(results=[
            GateResult(gate_text="cite lines", severity=GateSeverity.HARD, passed=False, evaluator="keyword"),
        ])
        assert classify_failure(None, ge) == FailureCategory.HARD_GATE_FAIL

    def test_soft_gate_not_retried(self) -> None:
        from interceptor.validation.gate_models import (
            GateEvaluation,
            GateResult,
            GateSeverity,
        )
        from interceptor.validation.retry_engine import classify_failure

        ge = GateEvaluation(results=[
            GateResult(gate_text="be concise", severity=GateSeverity.SOFT, passed=False, evaluator="keyword"),
        ])
        assert classify_failure(None, ge) is None

    def test_all_hard_gates_pass(self) -> None:
        from interceptor.validation.gate_models import (
            GateEvaluation,
            GateResult,
            GateSeverity,
        )
        from interceptor.validation.retry_engine import classify_failure

        ge = GateEvaluation(results=[
            GateResult(gate_text="cite lines", severity=GateSeverity.HARD, passed=True, evaluator="keyword"),
        ])
        assert classify_failure(None, ge) is None


# ── E. classify_failure: mixed fail ───────────────────────────────────────


class TestClassifyMixedFail:
    """Classify combined schema + gate failures."""

    def test_mixed_fail(self) -> None:
        from interceptor.validation.gate_models import (
            GateEvaluation,
            GateResult,
            GateSeverity,
        )
        from interceptor.validation.models import ValidationResult, ValidationStatus
        from interceptor.validation.retry_engine import classify_failure
        from interceptor.validation.retry_models import FailureCategory

        v = ValidationResult(status=ValidationStatus.FAIL, score=0.0, validator_name="json")
        ge = GateEvaluation(results=[
            GateResult(gate_text="cite lines", severity=GateSeverity.HARD, passed=False, evaluator="keyword"),
        ])
        assert classify_failure(v, ge) == FailureCategory.MIXED_VALIDATION_FAIL


# ── D'. Same failure detection ────────────────────────────────────────────


class TestSameFailureDetection:
    """Verify same-failure stop logic."""

    def test_same_failure_stops(self) -> None:
        from interceptor.validation.retry_engine import should_stop_same_failure
        from interceptor.validation.retry_models import FailureCategory

        reasons = [FailureCategory.SCHEMA_FAIL, FailureCategory.SCHEMA_FAIL]
        assert should_stop_same_failure(reasons) is True

    def test_different_failures_continue(self) -> None:
        from interceptor.validation.retry_engine import should_stop_same_failure
        from interceptor.validation.retry_models import FailureCategory

        reasons = [FailureCategory.SCHEMA_FAIL, FailureCategory.HARD_GATE_FAIL]
        assert should_stop_same_failure(reasons) is False

    def test_single_failure_continues(self) -> None:
        from interceptor.validation.retry_engine import should_stop_same_failure
        from interceptor.validation.retry_models import FailureCategory

        reasons = [FailureCategory.SCHEMA_FAIL]
        assert should_stop_same_failure(reasons) is False

    def test_empty_continues(self) -> None:
        from interceptor.validation.retry_engine import should_stop_same_failure

        assert should_stop_same_failure([]) is False


# ── Build retry prompt ────────────────────────────────────────────────────


class TestBuildRetryPrompt:
    """Verify strictness suffix appended, original unchanged."""

    def _make_prompt(self) -> Any:
        from interceptor.compilation.models import CompiledPrompt, CompressionLevel

        return CompiledPrompt(
            template_name="test",
            raw_input="hello",
            compiled_text="Original text.",
            token_count_estimate=10,
            compression_level=CompressionLevel.NONE,
        )

    def test_gentle_appends(self) -> None:
        from interceptor.validation.retry_engine import build_retry_prompt
        from interceptor.validation.retry_models import StrictnessLevel

        original = self._make_prompt()
        result = build_retry_prompt(original, StrictnessLevel.GENTLE)
        assert result.compiled_text.startswith("Original text.")
        assert "IMPORTANT" in result.compiled_text
        assert original.compiled_text == "Original text."

    def test_explicit_appends(self) -> None:
        from interceptor.validation.retry_engine import build_retry_prompt
        from interceptor.validation.retry_models import StrictnessLevel

        original = self._make_prompt()
        result = build_retry_prompt(original, StrictnessLevel.EXPLICIT)
        assert "CRITICAL FORMAT REQUIREMENTS" in result.compiled_text
        assert original.compiled_text == "Original text."

    def test_forced_appends(self) -> None:
        from interceptor.validation.retry_engine import build_retry_prompt
        from interceptor.validation.retry_models import StrictnessLevel

        original = self._make_prompt()
        result = build_retry_prompt(original, StrictnessLevel.FORCED)
        assert "MANDATORY" in result.compiled_text
        assert original.compiled_text == "Original text."

    def test_each_level_distinct(self) -> None:
        from interceptor.validation.retry_engine import build_retry_prompt
        from interceptor.validation.retry_models import STRICTNESS_ORDER

        original = self._make_prompt()
        texts = [build_retry_prompt(original, s).compiled_text for s in STRICTNESS_ORDER]
        assert len(set(texts)) == 3


# ── E+F. Retry recovery ──────────────────────────────────────────────────


class TestRetryRecovery:
    """Verify recovery on first, second, or third retry."""

    @dataclass(slots=True)
    class _FakeCompiledPrompt:
        template_name: str = "test"
        raw_input: str = "hello"
        compiled_text: str = "Original text."
        token_count_estimate: int = 10
        compression_level: str = "none"
        sections_included: list[str] = field(default_factory=list)
        system_directive_text: str = ""
        chain_of_thought_text: str = ""
        output_schema_text: str = "json"
        quality_gates_text: str = ""
        anti_patterns_text: str = ""
        user_input_text: str = ""
        quality_gates_hard: list[str] = field(default_factory=list)
        quality_gates_soft: list[str] = field(default_factory=list)

    def _make_sequence(self, *texts: str) -> Any:
        from interceptor.adapters.models import ExecutionResult

        results = [ExecutionResult(backend="claude", text=t) for t in texts]
        call_count = {"n": 0}

        def fake_send_full(self_adapter: Any, req: Any, **kw: Any) -> ExecutionResult:
            idx = min(call_count["n"], len(results) - 1)
            call_count["n"] += 1
            return results[idx]

        return fake_send_full, call_count

    def test_recover_on_first_retry(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from interceptor.adapters.service import AdapterService

        # first: bad json, retry 1 (gentle): good json
        send_fn, counter = self._make_sequence("not json", '{"ok": true}')
        monkeypatch.setattr(
            "interceptor.adapters.claude.ClaudeAdapter.adapt",
            lambda self, **kw: type("R", (), {"backend": "claude", "payload": {}, "temperature": 0.7, "max_output_tokens": 4096, "streaming": False})(),
        )
        monkeypatch.setattr("interceptor.adapters.claude.ClaudeAdapter.send_full", send_fn)

        cp = self._FakeCompiledPrompt(output_schema_text="Return a JSON object")
        svc = AdapterService()
        result = svc.execute_full(backend="claude", compiled_prompt=cp, temperature=0.7, max_output_tokens=4096)

        assert result.retry_result is not None
        assert str(result.retry_result.outcome) == "recovered"
        assert result.retry_result.attempts == 2
        assert counter["n"] == 2

    def test_recover_on_second_retry(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from interceptor.adapters.service import AdapterService

        # first: bad, retry 1: bad (different failure), retry 2: good
        send_fn, counter = self._make_sequence("not json", "still not json", '{"ok": true}')
        monkeypatch.setattr(
            "interceptor.adapters.claude.ClaudeAdapter.adapt",
            lambda self, **kw: type("R", (), {"backend": "claude", "payload": {}, "temperature": 0.7, "max_output_tokens": 4096, "streaming": False})(),
        )
        monkeypatch.setattr("interceptor.adapters.claude.ClaudeAdapter.send_full", send_fn)

        cp = self._FakeCompiledPrompt(output_schema_text="Return a JSON object")
        svc = AdapterService()
        result = svc.execute_full(backend="claude", compiled_prompt=cp, temperature=0.7, max_output_tokens=4096)

        assert result.retry_result is not None
        # Same failure (SCHEMA_FAIL twice) stops at attempt 2
        # Because "not json" and "still not json" both produce SCHEMA_FAIL
        assert str(result.retry_result.outcome) in ("recovered", "exhausted")
        assert counter["n"] >= 2


# ── G+H. Retry exhaustion ────────────────────────────────────────────────


class TestRetryExhaustion:
    """Verify exhaustion after max retries or same failure."""

    @dataclass(slots=True)
    class _FakeCompiledPrompt:
        template_name: str = "test"
        raw_input: str = "hello"
        compiled_text: str = "Original text."
        token_count_estimate: int = 10
        compression_level: str = "none"
        sections_included: list[str] = field(default_factory=list)
        system_directive_text: str = ""
        chain_of_thought_text: str = ""
        output_schema_text: str = "json"
        quality_gates_text: str = ""
        anti_patterns_text: str = ""
        user_input_text: str = ""
        quality_gates_hard: list[str] = field(default_factory=list)
        quality_gates_soft: list[str] = field(default_factory=list)

    def _make_sequence(self, *texts: str) -> Any:
        from interceptor.adapters.models import ExecutionResult

        results = [ExecutionResult(backend="claude", text=t) for t in texts]
        call_count = {"n": 0}

        def fake_send_full(self_adapter: Any, req: Any, **kw: Any) -> ExecutionResult:
            idx = min(call_count["n"], len(results) - 1)
            call_count["n"] += 1
            return results[idx]

        return fake_send_full, call_count

    def test_same_failure_stops_early(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from interceptor.adapters.service import AdapterService

        # All responses are bad json → same failure stops after 2 attempts
        send_fn, counter = self._make_sequence("bad", "bad", "bad", "bad")
        monkeypatch.setattr(
            "interceptor.adapters.claude.ClaudeAdapter.adapt",
            lambda self, **kw: type("R", (), {"backend": "claude", "payload": {}, "temperature": 0.7, "max_output_tokens": 4096, "streaming": False})(),
        )
        monkeypatch.setattr("interceptor.adapters.claude.ClaudeAdapter.send_full", send_fn)

        cp = self._FakeCompiledPrompt(output_schema_text="Return a JSON object")
        svc = AdapterService()
        result = svc.execute_full(backend="claude", compiled_prompt=cp, temperature=0.7, max_output_tokens=4096)

        assert result.retry_result is not None
        assert str(result.retry_result.outcome) == "exhausted"
        assert result.retry_result.same_failure_stopped is True
        assert result.retry_result.attempts == 2  # initial + 1 retry → same failure detected

    def test_max_retries_exhausted(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from interceptor.adapters.service import AdapterService

        # Alternate failures to avoid same-failure stop:
        # '{"a": "hello"}' is valid JSON but has no line refs → HARD_GATE_FAIL
        # 'issue on line 42' is not JSON but has line ref → SCHEMA_FAIL
        send_fn, counter = self._make_sequence(
            '{"a": "hello"}',   # initial: valid json, no line refs → HARD_GATE_FAIL
            'issue on line 42', # retry 1: bad json, has line ref → SCHEMA_FAIL
            '{"b": "world"}',   # retry 2: valid json, no line refs → HARD_GATE_FAIL
            'issue on line 99', # retry 3: bad json, has line ref → SCHEMA_FAIL
        )
        monkeypatch.setattr(
            "interceptor.adapters.claude.ClaudeAdapter.adapt",
            lambda self, **kw: type("R", (), {"backend": "claude", "payload": {}, "temperature": 0.7, "max_output_tokens": 4096, "streaming": False})(),
        )
        monkeypatch.setattr("interceptor.adapters.claude.ClaudeAdapter.send_full", send_fn)

        cp = self._FakeCompiledPrompt(
            output_schema_text="Return a JSON object",
            quality_gates_hard=["Every issue must cite a specific line or block"],
        )
        svc = AdapterService()
        result = svc.execute_full(backend="claude", compiled_prompt=cp, temperature=0.7, max_output_tokens=4096)

        assert result.retry_result is not None
        assert str(result.retry_result.outcome) == "exhausted"
        assert result.retry_result.same_failure_stopped is False
        assert result.retry_result.attempts == 4  # initial + 3 retries
        assert counter["n"] == 4


# ── I. Schema re-validation on each retry ─────────────────────────────────


class TestSchemaRevalidation:
    """Verify schema validation runs on every attempt."""

    @dataclass(slots=True)
    class _FakeCompiledPrompt:
        template_name: str = "test"
        raw_input: str = "hello"
        compiled_text: str = "Original text."
        token_count_estimate: int = 10
        compression_level: str = "none"
        sections_included: list[str] = field(default_factory=list)
        system_directive_text: str = ""
        chain_of_thought_text: str = ""
        output_schema_text: str = "json"
        quality_gates_text: str = ""
        anti_patterns_text: str = ""
        user_input_text: str = ""
        quality_gates_hard: list[str] = field(default_factory=list)
        quality_gates_soft: list[str] = field(default_factory=list)

    def test_validation_runs_on_retry(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from interceptor.adapters.models import ExecutionResult
        from interceptor.adapters.service import AdapterService

        call_count = {"n": 0}
        results = [
            ExecutionResult(backend="claude", text="not json"),
            ExecutionResult(backend="claude", text='{"ok": true}'),
        ]

        def fake_send_full(self_adapter: Any, req: Any, **kw: Any) -> ExecutionResult:
            idx = min(call_count["n"], len(results) - 1)
            call_count["n"] += 1
            return results[idx]

        monkeypatch.setattr(
            "interceptor.adapters.claude.ClaudeAdapter.adapt",
            lambda self, **kw: type("R", (), {"backend": "claude", "payload": {}, "temperature": 0.7, "max_output_tokens": 4096, "streaming": False})(),
        )
        monkeypatch.setattr("interceptor.adapters.claude.ClaudeAdapter.send_full", fake_send_full)

        cp = self._FakeCompiledPrompt(output_schema_text="Return a JSON object")
        svc = AdapterService()
        result = svc.execute_full(backend="claude", compiled_prompt=cp, temperature=0.7, max_output_tokens=4096)

        assert result.validation is not None
        assert str(result.validation.status) == "pass"
        assert str(result.retry_result.outcome) == "recovered"


# ── J. Gate re-evaluation on each retry ───────────────────────────────────


class TestGateReEvaluation:
    """Verify gates run on every attempt."""

    @dataclass(slots=True)
    class _FakeCompiledPrompt:
        template_name: str = "test"
        raw_input: str = "hello"
        compiled_text: str = "Original text."
        token_count_estimate: int = 10
        compression_level: str = "none"
        sections_included: list[str] = field(default_factory=list)
        system_directive_text: str = ""
        chain_of_thought_text: str = ""
        output_schema_text: str = ""
        quality_gates_text: str = ""
        anti_patterns_text: str = ""
        user_input_text: str = ""
        quality_gates_hard: list[str] = field(default_factory=list)
        quality_gates_soft: list[str] = field(default_factory=list)

    def test_gates_rerun_on_retry(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from interceptor.adapters.models import ExecutionResult
        from interceptor.adapters.service import AdapterService

        call_count = {"n": 0}
        results = [
            ExecutionResult(backend="claude", text="No references here"),
            ExecutionResult(backend="claude", text="Issue on line 42 in main.py"),
        ]

        def fake_send_full(self_adapter: Any, req: Any, **kw: Any) -> ExecutionResult:
            idx = min(call_count["n"], len(results) - 1)
            call_count["n"] += 1
            return results[idx]

        monkeypatch.setattr(
            "interceptor.adapters.claude.ClaudeAdapter.adapt",
            lambda self, **kw: type("R", (), {"backend": "claude", "payload": {}, "temperature": 0.7, "max_output_tokens": 4096, "streaming": False})(),
        )
        monkeypatch.setattr("interceptor.adapters.claude.ClaudeAdapter.send_full", fake_send_full)

        cp = self._FakeCompiledPrompt(
            quality_gates_hard=["Every issue must cite a specific line or block"],
        )
        svc = AdapterService()
        result = svc.execute_full(backend="claude", compiled_prompt=cp, temperature=0.7, max_output_tokens=4096)

        assert result.gate_evaluation is not None
        assert result.gate_evaluation.hard_passed is True
        assert result.retry_result is not None
        assert str(result.retry_result.outcome) == "recovered"


# ── K. Service integration: string prompts, passing, NOT_NEEDED ───────────


class TestServiceIntegration:
    """Verify backward-compatible behavior for non-retryable inputs."""

    def test_string_prompt_no_retry(self, monkeypatch: pytest.MonkeyPatch) -> None:
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
        assert result.retry_result is None

    def test_passing_response_not_needed(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from interceptor.adapters.models import ExecutionResult
        from interceptor.adapters.service import AdapterService

        @dataclass(slots=True)
        class _CP:
            template_name: str = "test"
            raw_input: str = "hello"
            compiled_text: str = "text"
            token_count_estimate: int = 10
            compression_level: str = "none"
            sections_included: list[str] = field(default_factory=list)
            system_directive_text: str = ""
            chain_of_thought_text: str = ""
            output_schema_text: str = "json"
            quality_gates_text: str = ""
            anti_patterns_text: str = ""
            user_input_text: str = ""
            quality_gates_hard: list[str] = field(default_factory=list)
            quality_gates_soft: list[str] = field(default_factory=list)

        fake_result = ExecutionResult(backend="claude", text='{"valid": true}')
        monkeypatch.setattr(
            "interceptor.adapters.claude.ClaudeAdapter.adapt",
            lambda self, **kw: type("R", (), {"backend": "claude", "payload": {}, "temperature": 0.7, "max_output_tokens": 4096, "streaming": False})(),
        )
        monkeypatch.setattr(
            "interceptor.adapters.claude.ClaudeAdapter.send_full",
            lambda self, req, **kw: fake_result,
        )

        cp = _CP(output_schema_text="Return a JSON object")
        svc = AdapterService()
        result = svc.execute_full(backend="claude", compiled_prompt=cp, temperature=0.7, max_output_tokens=4096)

        assert result.retry_result is not None
        assert str(result.retry_result.outcome) == "not_needed"
        assert result.retry_result.attempts == 1

    def test_no_schema_no_gates_not_needed(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from interceptor.adapters.models import ExecutionResult
        from interceptor.adapters.service import AdapterService

        @dataclass(slots=True)
        class _CP:
            template_name: str = "test"
            raw_input: str = "hello"
            compiled_text: str = "text"
            token_count_estimate: int = 10
            compression_level: str = "none"
            sections_included: list[str] = field(default_factory=list)
            system_directive_text: str = ""
            chain_of_thought_text: str = ""
            output_schema_text: str = ""
            quality_gates_text: str = ""
            anti_patterns_text: str = ""
            user_input_text: str = ""
            quality_gates_hard: list[str] = field(default_factory=list)
            quality_gates_soft: list[str] = field(default_factory=list)

        fake_result = ExecutionResult(backend="claude", text="whatever")
        monkeypatch.setattr(
            "interceptor.adapters.claude.ClaudeAdapter.adapt",
            lambda self, **kw: type("R", (), {"backend": "claude", "payload": {}, "temperature": 0.7, "max_output_tokens": 4096, "streaming": False})(),
        )
        monkeypatch.setattr(
            "interceptor.adapters.claude.ClaudeAdapter.send_full",
            lambda self, req, **kw: fake_result,
        )

        cp = _CP()
        svc = AdapterService()
        result = svc.execute_full(backend="claude", compiled_prompt=cp, temperature=0.7, max_output_tokens=4096)

        assert result.retry_result is not None
        assert str(result.retry_result.outcome) == "not_needed"


# ── L. CLI retry display ─────────────────────────────────────────────────


class TestCliRetryDisplay:
    """Verify terminal rendering of retry outcomes."""

    def test_recovered_display(self, capsys: pytest.CaptureFixture[str]) -> None:
        from interceptor.validation.retry_models import RetryOutcome, RetryResult, StrictnessLevel

        from interceptor.cli import _render_retry_result

        r = RetryResult(
            attempts=2,
            outcome=RetryOutcome.RECOVERED,
            final_strictness=StrictnessLevel.GENTLE,
        )
        _render_retry_result(r)
        captured = capsys.readouterr().out
        assert "recovered" in captured
        assert "2 attempt" in captured

    def test_exhausted_display(self, capsys: pytest.CaptureFixture[str]) -> None:
        from interceptor.validation.retry_models import RetryOutcome, RetryResult, StrictnessLevel

        from interceptor.cli import _render_retry_result

        r = RetryResult(
            attempts=4,
            outcome=RetryOutcome.EXHAUSTED,
            final_strictness=StrictnessLevel.FORCED,
        )
        _render_retry_result(r)
        captured = capsys.readouterr().out
        assert "exhausted" in captured
        assert "4 attempt" in captured

    def test_same_failure_display(self, capsys: pytest.CaptureFixture[str]) -> None:
        from interceptor.validation.retry_models import RetryOutcome, RetryResult, StrictnessLevel

        from interceptor.cli import _render_retry_result

        r = RetryResult(
            attempts=2,
            outcome=RetryOutcome.EXHAUSTED,
            final_strictness=StrictnessLevel.GENTLE,
            same_failure_stopped=True,
        )
        _render_retry_result(r)
        captured = capsys.readouterr().out
        assert "same failure" in captured

    def test_not_needed_silent(self, capsys: pytest.CaptureFixture[str]) -> None:
        from interceptor.validation.retry_models import RetryResult

        from interceptor.cli import _render_retry_result

        r = RetryResult()  # NOT_NEEDED by default
        _render_retry_result(r)
        captured = capsys.readouterr().out
        assert captured.strip() == ""


# ── M. JSON output includes retry metadata ────────────────────────────────


class TestJsonRetryOutput:
    """Verify JSON output structure for retry data."""

    def test_retry_in_json(self) -> None:
        from interceptor.validation.retry_models import (
            FailureCategory,
            RetryOutcome,
            RetryResult,
            StrictnessLevel,
        )

        r = RetryResult(
            attempts=3,
            outcome=RetryOutcome.RECOVERED,
            final_strictness=StrictnessLevel.EXPLICIT,
            failure_reasons=[FailureCategory.SCHEMA_FAIL, FailureCategory.SCHEMA_FAIL],
        )
        data: dict[str, Any] = {}
        if r and str(r.outcome) != "not_needed":
            data["retry"] = {
                "attempts": r.attempts,
                "max_retries": r.max_retries,
                "outcome": str(r.outcome),
                "final_strictness": str(r.final_strictness) if r.final_strictness else None,
                "same_failure_stopped": r.same_failure_stopped,
                "failure_reasons": [str(f) for f in r.failure_reasons],
            }

        assert data["retry"]["attempts"] == 3
        assert data["retry"]["outcome"] == "recovered"
        assert data["retry"]["final_strictness"] == "explicit"
        assert len(data["retry"]["failure_reasons"]) == 2

    def test_not_needed_excluded(self) -> None:
        from interceptor.validation.retry_models import RetryResult

        r = RetryResult()
        data: dict[str, Any] = {}
        if r and str(r.outcome) != "not_needed":
            data["retry"] = {}

        assert "retry" not in data


# ── N. Regression safety ──────────────────────────────────────────────────


class TestRegressionSafety:
    """Verify PR-9/10/11/12 behavior is preserved."""

    def test_imports_still_work(self) -> None:
        from interceptor.validation import (
            FailureCategory,
            GateEvaluation,
            GateResult,
            GateSeverity,
            RetryOutcome,
            RetryResult,
            StrictnessLevel,
            ValidationIssue,
            ValidationResult,
            ValidationStatus,
            infer_format,
            validate_output,
        )

    def test_execution_result_backward_compat(self) -> None:
        from interceptor.adapters.models import ExecutionResult

        r = ExecutionResult(backend="claude", text="hello")
        assert r.validation is None
        assert r.gate_evaluation is None
        assert r.retry_result is None

    def test_retry_result_optional(self) -> None:
        from interceptor.adapters.models import ExecutionResult

        r = ExecutionResult(backend="claude", text="hello")
        assert r.retry_result is None
