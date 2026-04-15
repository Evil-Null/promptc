"""PR-25 tests — plugin validation integration: prevalidate/postvalidate wiring."""

from __future__ import annotations

import json
import textwrap
from pathlib import Path

import httpx
import pytest

from interceptor.adapters.models import ExecutionResult
from interceptor.adapters.service import AdapterService
from interceptor.compilation.models import CompiledPrompt, CompressionLevel
from interceptor.plugins.integration import build_plugin_runner, execute_with_plugins
from interceptor.validation.gate_models import GateEvaluation, GateResult, GateSeverity
from interceptor.validation.models import ValidationResult, ValidationStatus


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_VALID_TOML = """\
name = "{name}"
version = "1.0.0"
description = "Test plugin"
hooks = [{hooks}]
api_version = "v1"
min_compiler_version = "0.1.0"
max_compiler_version = "99.0.0"
"""

CLAUDE_OK_BODY = {
    "content": [{"type": "text", "text": "Hello from Claude"}],
    "stop_reason": "end_turn",
    "usage": {"input_tokens": 15, "output_tokens": 8},
}


def _write_plugin(
    plugin_dir: Path,
    name: str,
    hooks: str,
    code: str,
) -> Path:
    plugin_dir.mkdir(parents=True, exist_ok=True)
    (plugin_dir / "plugin.toml").write_text(_VALID_TOML.format(name=name, hooks=hooks))
    (plugin_dir / "plugin.py").write_text(textwrap.dedent(code))
    return plugin_dir


def _mock_client(body: dict | None = None) -> httpx.Client:
    response_body = body or CLAUDE_OK_BODY

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=response_body)

    return httpx.Client(transport=httpx.MockTransport(handler))


def _make_prompt(
    *,
    output_schema_text: str = "",
    quality_gates_hard: list[str] | None = None,
    quality_gates_soft: list[str] | None = None,
) -> CompiledPrompt:
    """Build a minimal real CompiledPrompt for testing."""
    return CompiledPrompt(
        template_name="test",
        raw_input="test",
        compiled_text="test",
        token_count_estimate=10,
        compression_level=CompressionLevel.NONE,
        user_input_text="test",
        output_schema_text=output_schema_text,
        quality_gates_hard=quality_gates_hard or [],
        quality_gates_soft=quality_gates_soft or [],
    )


# ===================================================================
# A — Validation unchanged when no plugins directory exists
# ===================================================================

class TestA_NoPluginsDir:
    """No plugins dir → validation behavior unchanged."""

    def test_no_dir(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
        nonexistent = tmp_path / "nope"

        prompt = _make_prompt(
            output_schema_text="json",
        )

        body = {"content": [{"type": "text", "text": '{"key":"value"}'}],
                "stop_reason": "end_turn",
                "usage": {"input_tokens": 1, "output_tokens": 1}}

        result = execute_with_plugins(
            service=AdapterService(),
            backend="claude",
            compiled_prompt=prompt,
            temperature=0.7,
            max_output_tokens=4096,
            client=_mock_client(body),
            plugins_dir=nonexistent,
        )
        assert result.validation is not None
        assert result.validation.status == ValidationStatus.PASS


# ===================================================================
# B — Validation unchanged when plugins dir empty
# ===================================================================

class TestB_EmptyPluginsDir:
    """Empty plugins dir → validation behavior unchanged."""

    def test_empty(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
        plugins_dir = tmp_path / "plugins"
        plugins_dir.mkdir()

        prompt = _make_prompt(
            output_schema_text="json",
        )
        body = {"content": [{"type": "text", "text": '{"a":1}'}],
                "stop_reason": "end_turn",
                "usage": {"input_tokens": 1, "output_tokens": 1}}

        result = execute_with_plugins(
            service=AdapterService(),
            backend="claude",
            compiled_prompt=prompt,
            temperature=0.7,
            max_output_tokens=4096,
            client=_mock_client(body),
            plugins_dir=plugins_dir,
        )
        assert result.validation is not None
        assert result.validation.status == ValidationStatus.PASS


# ===================================================================
# C — Prevalidate modifies text before validation
# ===================================================================

class TestC_PrevalidateModifiesText:
    """Prevalidate plugin modifies text before schema validation."""

    def test_prevalidate_effect(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
        plugins_dir = tmp_path / "plugins"
        _write_plugin(
            plugins_dir / "fixer",
            "fixer",
            '"prevalidate"',
            """\
            class Plugin:
                def prevalidate(self, text, ctx):
                    return '{"fixed": true}'
            """,
        )
        prompt = _make_prompt(
            output_schema_text="json",
        )
        body = {"content": [{"type": "text", "text": "not json at all"}],
                "stop_reason": "end_turn",
                "usage": {"input_tokens": 1, "output_tokens": 1}}

        result = execute_with_plugins(
            service=AdapterService(),
            backend="claude",
            compiled_prompt=prompt,
            temperature=0.7,
            max_output_tokens=4096,
            client=_mock_client(body),
            plugins_dir=plugins_dir,
        )
        assert result.text == '{"fixed": true}'
        assert result.validation is not None
        assert result.validation.status == ValidationStatus.PASS


# ===================================================================
# D — Postvalidate modifies result after validation
# ===================================================================

class TestD_PostvalidateModifiesResult:
    """Postvalidate plugin can modify the ExecutionResult after validation."""

    def test_postvalidate_effect(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
        plugins_dir = tmp_path / "plugins"
        _write_plugin(
            plugins_dir / "modifier",
            "modifier",
            '"postvalidate"',
            """\
            class Plugin:
                def postvalidate(self, result, ctx):
                    result.text = result.text + " [POST-VALIDATED]"
                    return result
            """,
        )
        prompt = _make_prompt(
            output_schema_text="json",
        )
        body = {"content": [{"type": "text", "text": '{"a":1}'}],
                "stop_reason": "end_turn",
                "usage": {"input_tokens": 1, "output_tokens": 1}}

        result = execute_with_plugins(
            service=AdapterService(),
            backend="claude",
            compiled_prompt=prompt,
            temperature=0.7,
            max_output_tokens=4096,
            client=_mock_client(body),
            plugins_dir=plugins_dir,
        )
        assert "[POST-VALIDATED]" in result.text
        assert result.validation is not None


# ===================================================================
# E — Multiple prevalidate plugins run in order
# ===================================================================

class TestE_MultiPrevalidateOrder:
    """Multiple prevalidate plugins chain in alphabetical order."""

    def test_multi_prevalidate(self, tmp_path: Path) -> None:
        plugins_dir = tmp_path / "plugins"
        _write_plugin(
            plugins_dir / "aa",
            "aa",
            '"prevalidate"',
            """\
            class Plugin:
                def prevalidate(self, text, ctx):
                    return text + " >A"
            """,
        )
        _write_plugin(
            plugins_dir / "bb",
            "bb",
            '"prevalidate"',
            """\
            class Plugin:
                def prevalidate(self, text, ctx):
                    return text + " >B"
            """,
        )
        runner = build_plugin_runner(plugins_dir)
        out = runner.run_hook("prevalidate", "start")
        assert out == "start >A >B"


# ===================================================================
# F — Multiple postvalidate plugins run in order
# ===================================================================

class TestF_MultiPostvalidateOrder:
    """Multiple postvalidate plugins chain in order."""

    def test_multi_postvalidate(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
        plugins_dir = tmp_path / "plugins"
        _write_plugin(
            plugins_dir / "aa",
            "aa",
            '"postvalidate"',
            """\
            class Plugin:
                def postvalidate(self, result, ctx):
                    result.text = result.text + " +AA"
                    return result
            """,
        )
        _write_plugin(
            plugins_dir / "bb",
            "bb",
            '"postvalidate"',
            """\
            class Plugin:
                def postvalidate(self, result, ctx):
                    result.text = result.text + " +BB"
                    return result
            """,
        )
        prompt = _make_prompt(output_schema_text="json")
        body = {"content": [{"type": "text", "text": '{"a":1}'}],
                "stop_reason": "end_turn",
                "usage": {"input_tokens": 1, "output_tokens": 1}}

        result = execute_with_plugins(
            service=AdapterService(),
            backend="claude",
            compiled_prompt=prompt,
            temperature=0.7,
            max_output_tokens=4096,
            client=_mock_client(body),
            plugins_dir=plugins_dir,
        )
        assert result.text.endswith("+AA +BB")


# ===================================================================
# G — Prevalidate B sees A's output
# ===================================================================

class TestG_PrevalidateChaining:
    """Plugin B receives the output of plugin A."""

    def test_chain(self, tmp_path: Path) -> None:
        plugins_dir = tmp_path / "plugins"
        _write_plugin(
            plugins_dir / "aa",
            "aa",
            '"prevalidate"',
            """\
            class Plugin:
                def prevalidate(self, text, ctx):
                    return text.upper()
            """,
        )
        _write_plugin(
            plugins_dir / "bb",
            "bb",
            '"prevalidate"',
            """\
            class Plugin:
                def prevalidate(self, text, ctx):
                    if text.isupper():
                        return text + " [SAW-UPPER]"
                    return text
            """,
        )
        runner = build_plugin_runner(plugins_dir)
        out = runner.run_hook("prevalidate", "hello")
        assert out == "HELLO [SAW-UPPER]"


# ===================================================================
# H — Postvalidate B sees A's output
# ===================================================================

class TestH_PostvalidateChaining:
    """Postvalidate B receives A's modified result."""

    def test_post_chain(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
        plugins_dir = tmp_path / "plugins"
        _write_plugin(
            plugins_dir / "aa",
            "aa",
            '"postvalidate"',
            """\
            class Plugin:
                def postvalidate(self, result, ctx):
                    result.finish_reason = "aa-was-here"
                    return result
            """,
        )
        _write_plugin(
            plugins_dir / "bb",
            "bb",
            '"postvalidate"',
            """\
            class Plugin:
                def postvalidate(self, result, ctx):
                    if result.finish_reason == "aa-was-here":
                        result.text = result.text + " [BB-SAW-AA]"
                    return result
            """,
        )
        prompt = _make_prompt(output_schema_text="json")
        body = {"content": [{"type": "text", "text": '{"a":1}'}],
                "stop_reason": "end_turn",
                "usage": {"input_tokens": 1, "output_tokens": 1}}

        result = execute_with_plugins(
            service=AdapterService(),
            backend="claude",
            compiled_prompt=prompt,
            temperature=0.7,
            max_output_tokens=4096,
            client=_mock_client(body),
            plugins_dir=plugins_dir,
        )
        assert "[BB-SAW-AA]" in result.text
        assert result.finish_reason == "aa-was-here"


# ===================================================================
# I — Failing prevalidate → disabled, validation continues
# ===================================================================

class TestI_PrevalidateCrash:
    """Crashing prevalidate plugin disabled; validation uses original text."""

    def test_crash_continues(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
        plugins_dir = tmp_path / "plugins"
        _write_plugin(
            plugins_dir / "crasher",
            "crasher",
            '"prevalidate"',
            """\
            class Plugin:
                def prevalidate(self, text, ctx):
                    raise RuntimeError("boom")
            """,
        )
        prompt = _make_prompt(output_schema_text="json")
        body = {"content": [{"type": "text", "text": '{"valid":true}'}],
                "stop_reason": "end_turn",
                "usage": {"input_tokens": 1, "output_tokens": 1}}

        result = execute_with_plugins(
            service=AdapterService(),
            backend="claude",
            compiled_prompt=prompt,
            temperature=0.7,
            max_output_tokens=4096,
            client=_mock_client(body),
            plugins_dir=plugins_dir,
        )
        assert result.validation is not None
        assert result.validation.status == ValidationStatus.PASS


# ===================================================================
# J — Failing postvalidate → last good result preserved
# ===================================================================

class TestJ_PostvalidateCrash:
    """Crashing postvalidate plugin disabled; result unchanged."""

    def test_crash_continues(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
        plugins_dir = tmp_path / "plugins"
        _write_plugin(
            plugins_dir / "crasher",
            "crasher",
            '"postvalidate"',
            """\
            class Plugin:
                def postvalidate(self, result, ctx):
                    raise ValueError("oops")
            """,
        )
        prompt = _make_prompt(output_schema_text="json")
        body = {"content": [{"type": "text", "text": '{"a":1}'}],
                "stop_reason": "end_turn",
                "usage": {"input_tokens": 1, "output_tokens": 1}}

        result = execute_with_plugins(
            service=AdapterService(),
            backend="claude",
            compiled_prompt=prompt,
            temperature=0.7,
            max_output_tokens=4096,
            client=_mock_client(body),
            plugins_dir=plugins_dir,
        )
        assert result.validation is not None
        assert result.validation.status == ValidationStatus.PASS


# ===================================================================
# K — None from prevalidate → treated as failure
# ===================================================================

class TestK_PrevalidateNone:
    """Prevalidate returning None → original text used."""

    def test_none(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
        plugins_dir = tmp_path / "plugins"
        _write_plugin(
            plugins_dir / "noner",
            "noner",
            '"prevalidate"',
            """\
            class Plugin:
                def prevalidate(self, text, ctx):
                    return None
            """,
        )
        prompt = _make_prompt(output_schema_text="json")
        body = {"content": [{"type": "text", "text": '{"a":1}'}],
                "stop_reason": "end_turn",
                "usage": {"input_tokens": 1, "output_tokens": 1}}

        result = execute_with_plugins(
            service=AdapterService(),
            backend="claude",
            compiled_prompt=prompt,
            temperature=0.7,
            max_output_tokens=4096,
            client=_mock_client(body),
            plugins_dir=plugins_dir,
        )
        assert result.text == '{"a":1}'
        assert result.validation.status == ValidationStatus.PASS


# ===================================================================
# L — None from postvalidate → treated as failure
# ===================================================================

class TestL_PostvalidateNone:
    """Postvalidate returning None → result preserved."""

    def test_none(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
        plugins_dir = tmp_path / "plugins"
        _write_plugin(
            plugins_dir / "noner",
            "noner",
            '"postvalidate"',
            """\
            class Plugin:
                def postvalidate(self, result, ctx):
                    return None
            """,
        )
        prompt = _make_prompt(output_schema_text="json")
        body = {"content": [{"type": "text", "text": '{"a":1}'}],
                "stop_reason": "end_turn",
                "usage": {"input_tokens": 1, "output_tokens": 1}}

        result = execute_with_plugins(
            service=AdapterService(),
            backend="claude",
            compiled_prompt=prompt,
            temperature=0.7,
            max_output_tokens=4096,
            client=_mock_client(body),
            plugins_dir=plugins_dir,
        )
        assert result.validation is not None
        assert result.validation.status == ValidationStatus.PASS


# ===================================================================
# M — One plugin failing doesn't disable healthy plugins
# ===================================================================

class TestM_HealthyPluginsSurvive:
    """Crashing plugin B doesn't disable healthy plugins A/C."""

    def test_healthy_survive(self, tmp_path: Path) -> None:
        plugins_dir = tmp_path / "plugins"
        _write_plugin(
            plugins_dir / "aa-good",
            "aa-good",
            '"prevalidate"',
            """\
            class Plugin:
                def prevalidate(self, text, ctx):
                    return text + " >A"
            """,
        )
        _write_plugin(
            plugins_dir / "bb-bad",
            "bb-bad",
            '"prevalidate"',
            """\
            class Plugin:
                def prevalidate(self, text, ctx):
                    raise RuntimeError("crash")
            """,
        )
        _write_plugin(
            plugins_dir / "cc-good",
            "cc-good",
            '"prevalidate"',
            """\
            class Plugin:
                def prevalidate(self, text, ctx):
                    return text + " >C"
            """,
        )
        runner = build_plugin_runner(plugins_dir)
        out = runner.run_hook("prevalidate", "start")
        assert out == "start >A >C"


# ===================================================================
# N — Next invocation starts fresh
# ===================================================================

class TestN_FreshInvocation:
    """Each execute_with_plugins call creates a fresh runner."""

    def test_fresh(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
        plugins_dir = tmp_path / "plugins"
        _write_plugin(
            plugins_dir / "marker",
            "marker",
            '"postvalidate"',
            """\
            class Plugin:
                def postvalidate(self, result, ctx):
                    result.text = result.text + " [VAL-PLUGIN]"
                    return result
            """,
        )
        prompt = _make_prompt(output_schema_text="json")
        body = {"content": [{"type": "text", "text": '{"a":1}'}],
                "stop_reason": "end_turn",
                "usage": {"input_tokens": 1, "output_tokens": 1}}
        client = _mock_client(body)

        r1 = execute_with_plugins(
            service=AdapterService(), backend="claude",
            compiled_prompt=prompt, temperature=0.7,
            max_output_tokens=4096, client=client,
            plugins_dir=plugins_dir,
        )
        r2 = execute_with_plugins(
            service=AdapterService(), backend="claude",
            compiled_prompt=prompt, temperature=0.7,
            max_output_tokens=4096, client=client,
            plugins_dir=plugins_dir,
        )
        assert "[VAL-PLUGIN]" in r1.text
        assert "[VAL-PLUGIN]" in r2.text


# ===================================================================
# O — End-to-end proof through live validation seam
# ===================================================================

class TestO_EndToEnd:
    """Real validation pipeline shows plugin effect end-to-end."""

    def test_e2e(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
        plugins_dir = tmp_path / "plugins"
        _write_plugin(
            plugins_dir / "dual",
            "dual",
            '"prevalidate", "postvalidate"',
            """\
            class Plugin:
                def prevalidate(self, text, ctx):
                    return '{"injected": true}'

                def postvalidate(self, result, ctx):
                    result.text = result.text + " [POST-VALIDATED]"
                    return result
            """,
        )
        prompt = _make_prompt(
            output_schema_text="json",
        )
        body = {"content": [{"type": "text", "text": "not json"}],
                "stop_reason": "end_turn",
                "usage": {"input_tokens": 1, "output_tokens": 1}}

        result = execute_with_plugins(
            service=AdapterService(),
            backend="claude",
            compiled_prompt=prompt,
            temperature=0.7,
            max_output_tokens=4096,
            client=_mock_client(body),
            plugins_dir=plugins_dir,
        )
        assert result.validation is not None
        assert result.validation.status == ValidationStatus.PASS
        assert "[POST-VALIDATED]" in result.text

        # Without plugins: same backend response would fail JSON validation
        empty = tmp_path / "empty"
        empty.mkdir()
        result_no_plugin = execute_with_plugins(
            service=AdapterService(),
            backend="claude",
            compiled_prompt=prompt,
            temperature=0.7,
            max_output_tokens=4096,
            client=_mock_client(body),
            plugins_dir=empty,
        )
        assert result_no_plugin.validation.status == ValidationStatus.FAIL


# ===================================================================
# P — Regression safety for existing validation behavior
# ===================================================================

class TestP_Regression:
    """execute_with_plugins with no plugins matches execute_full validation."""

    def test_field_identical(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
        empty = tmp_path / "empty"
        empty.mkdir()

        prompt = _make_prompt(
            output_schema_text="json",
        )
        body = {"content": [{"type": "text", "text": '{"a":1}'}],
                "stop_reason": "end_turn",
                "usage": {"input_tokens": 1, "output_tokens": 1}}
        client = _mock_client(body)
        service = AdapterService()

        with_wrapper = execute_with_plugins(
            service=service, backend="claude",
            compiled_prompt=prompt, temperature=0.7,
            max_output_tokens=4096, client=client,
            plugins_dir=empty,
        )
        baseline = service.execute_full(
            backend="claude", compiled_prompt=prompt,
            temperature=0.7, max_output_tokens=4096, client=client,
        )
        assert with_wrapper.text == baseline.text
        assert with_wrapper.validation.status == baseline.validation.status
        assert with_wrapper.validation.score == baseline.validation.score


# ===================================================================
# Q — Downstream type/shape integrity after postvalidate
# ===================================================================

class TestQ_ResultIntegrity:
    """ExecutionResult type preserved after postvalidate use."""

    def test_type_preserved(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
        plugins_dir = tmp_path / "plugins"
        _write_plugin(
            plugins_dir / "modifier",
            "modifier",
            '"postvalidate"',
            """\
            class Plugin:
                def postvalidate(self, result, ctx):
                    result.text = result.text + " [MODIFIED]"
                    return result
            """,
        )
        prompt = _make_prompt(output_schema_text="json")
        body = {"content": [{"type": "text", "text": '{"a":1}'}],
                "stop_reason": "end_turn",
                "usage": {"input_tokens": 1, "output_tokens": 1}}

        result = execute_with_plugins(
            service=AdapterService(),
            backend="claude",
            compiled_prompt=prompt,
            temperature=0.7,
            max_output_tokens=4096,
            client=_mock_client(body),
            plugins_dir=plugins_dir,
        )
        assert isinstance(result, ExecutionResult)
        assert isinstance(result.text, str)
        assert isinstance(result.validation, ValidationResult)
        assert "[MODIFIED]" in result.text


# ===================================================================
# R — No-plugin users see unchanged output/formatting
# ===================================================================

class TestR_NoPluginUnchanged:
    """No-plugin validation output identical for plain string prompt."""

    def test_string_prompt_unchanged(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
        empty = tmp_path / "empty"
        empty.mkdir()
        client = _mock_client()
        service = AdapterService()

        with_wrapper = execute_with_plugins(
            service=service, backend="claude",
            compiled_prompt="plain string",
            temperature=0.7, max_output_tokens=4096,
            client=client, plugins_dir=empty,
        )
        baseline = service.execute_full(
            backend="claude", compiled_prompt="plain string",
            temperature=0.7, max_output_tokens=4096, client=client,
        )
        assert with_wrapper.text == baseline.text
        assert with_wrapper.validation is None
        assert baseline.validation is None
