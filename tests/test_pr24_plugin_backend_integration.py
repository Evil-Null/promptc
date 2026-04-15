"""PR-24 tests — plugin backend integration: presend/postreceive wiring."""

from __future__ import annotations

import json
import textwrap
from pathlib import Path
from typing import Any

import httpx
import pytest

from interceptor.adapters.models import (
    AdaptedRequest,
    BackendName,
    ExecutionResult,
    StreamEvent,
)
from interceptor.adapters.service import AdapterService
from interceptor.plugins.integration import (
    build_plugin_runner,
    execute_stream_with_plugins,
    execute_with_plugins,
)


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
    """Write plugin.toml + plugin.py in one call."""
    plugin_dir.mkdir(parents=True, exist_ok=True)
    (plugin_dir / "plugin.toml").write_text(_VALID_TOML.format(name=name, hooks=hooks))
    (plugin_dir / "plugin.py").write_text(textwrap.dedent(code))
    return plugin_dir


def _mock_client(body: dict | None = None, status: int = 200) -> httpx.Client:
    """Create a mock httpx.Client returning a canned Claude response."""
    response_body = body or CLAUDE_OK_BODY

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status, json=response_body)

    return httpx.Client(transport=httpx.MockTransport(handler))


def _service() -> AdapterService:
    return AdapterService()


# ===================================================================
# A — Backend unchanged when no plugins directory exists
# ===================================================================

class TestA_NoPluginsDir:
    """execute_with_plugins without plugins dir matches execute_full()."""

    def test_no_dir_unchanged(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
        nonexistent = tmp_path / "nope"
        client = _mock_client()
        service = _service()

        result = execute_with_plugins(
            service=service,
            backend="claude",
            compiled_prompt="test prompt",
            temperature=0.7,
            max_output_tokens=4096,
            client=client,
            plugins_dir=nonexistent,
        )
        assert isinstance(result, ExecutionResult)
        assert result.text == "Hello from Claude"
        assert result.backend == "claude"


# ===================================================================
# B — Backend unchanged when plugins dir exists but empty
# ===================================================================

class TestB_EmptyPluginsDir:
    """Empty plugins dir → backend unchanged."""

    def test_empty_dir_unchanged(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
        plugins_dir = tmp_path / "plugins"
        plugins_dir.mkdir()
        client = _mock_client()

        result = execute_with_plugins(
            service=_service(),
            backend="claude",
            compiled_prompt="test prompt",
            temperature=0.7,
            max_output_tokens=4096,
            client=client,
            plugins_dir=plugins_dir,
        )
        assert result.text == "Hello from Claude"


# ===================================================================
# C — Presend hook modifies compiled prompt before backend send
# ===================================================================

class TestC_PresendModifiesPrompt:
    """Presend plugin modifies compiled prompt used by backend."""

    def test_presend_effect(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
        plugins_dir = tmp_path / "plugins"

        captured_payloads: list[dict] = []

        def handler(request: httpx.Request) -> httpx.Response:
            captured_payloads.append(json.loads(request.content))
            return httpx.Response(200, json=CLAUDE_OK_BODY)

        client = httpx.Client(transport=httpx.MockTransport(handler))

        _write_plugin(
            plugins_dir / "injector",
            "injector",
            '"presend"',
            """\
            class Plugin:
                def presend(self, compiled_prompt, ctx):
                    return "MODIFIED BY PLUGIN"
            """,
        )
        execute_with_plugins(
            service=_service(),
            backend="claude",
            compiled_prompt="original prompt",
            temperature=0.7,
            max_output_tokens=4096,
            client=client,
            plugins_dir=plugins_dir,
        )
        assert len(captured_payloads) == 1
        payload = captured_payloads[0]
        assert "MODIFIED BY PLUGIN" in payload["system"]


# ===================================================================
# D — Postreceive hook modifies ExecutionResult
# ===================================================================

class TestD_PostreceiveModifiesResult:
    """Postreceive plugin can modify the ExecutionResult."""

    def test_postreceive_effect(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
        plugins_dir = tmp_path / "plugins"
        _write_plugin(
            plugins_dir / "overrider",
            "overrider",
            '"postreceive"',
            """\
            class Plugin:
                def postreceive(self, result, ctx):
                    result.text = "OVERRIDDEN BY PLUGIN"
                    return result
            """,
        )
        result = execute_with_plugins(
            service=_service(),
            backend="claude",
            compiled_prompt="test",
            temperature=0.7,
            max_output_tokens=4096,
            client=_mock_client(),
            plugins_dir=plugins_dir,
        )
        assert result.text == "OVERRIDDEN BY PLUGIN"


# ===================================================================
# E — Multiple presend plugins run in order
# ===================================================================

class TestE_MultiPresendOrder:
    """Multiple presend plugins chain in alphabetical discovery order."""

    def test_multi_presend(self, tmp_path: Path) -> None:
        plugins_dir = tmp_path / "plugins"
        _write_plugin(
            plugins_dir / "aa-first",
            "aa-first",
            '"presend"',
            """\
            class Plugin:
                def presend(self, prompt, ctx):
                    return prompt + " >A"
            """,
        )
        _write_plugin(
            plugins_dir / "bb-second",
            "bb-second",
            '"presend"',
            """\
            class Plugin:
                def presend(self, prompt, ctx):
                    return prompt + " >B"
            """,
        )
        runner = build_plugin_runner(plugins_dir)
        out = runner.run_hook("presend", "start")
        assert out == "start >A >B"


# ===================================================================
# F — Multiple postreceive plugins run in order
# ===================================================================

class TestF_MultiPostreceiveOrder:
    """Multiple postreceive plugins chain in order."""

    def test_multi_postreceive(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
        plugins_dir = tmp_path / "plugins"
        _write_plugin(
            plugins_dir / "aa-first",
            "aa-first",
            '"postreceive"',
            """\
            class Plugin:
                def postreceive(self, result, ctx):
                    result.text = result.text + " +AA"
                    return result
            """,
        )
        _write_plugin(
            plugins_dir / "bb-second",
            "bb-second",
            '"postreceive"',
            """\
            class Plugin:
                def postreceive(self, result, ctx):
                    result.text = result.text + " +BB"
                    return result
            """,
        )
        result = execute_with_plugins(
            service=_service(),
            backend="claude",
            compiled_prompt="test",
            temperature=0.7,
            max_output_tokens=4096,
            client=_mock_client(),
            plugins_dir=plugins_dir,
        )
        assert result.text == "Hello from Claude +AA +BB"


# ===================================================================
# G — Presend B sees A's output
# ===================================================================

class TestG_PresendChaining:
    """Plugin B receives the output of plugin A."""

    def test_chain_visibility(self, tmp_path: Path) -> None:
        plugins_dir = tmp_path / "plugins"
        _write_plugin(
            plugins_dir / "aa",
            "aa",
            '"presend"',
            """\
            class Plugin:
                def presend(self, prompt, ctx):
                    return prompt.upper()
            """,
        )
        _write_plugin(
            plugins_dir / "bb",
            "bb",
            '"presend"',
            """\
            class Plugin:
                def presend(self, prompt, ctx):
                    if prompt.isupper():
                        return prompt + " [SAW-UPPER]"
                    return prompt + " [NO-UPPER]"
            """,
        )
        runner = build_plugin_runner(plugins_dir)
        out = runner.run_hook("presend", "hello")
        assert out == "HELLO [SAW-UPPER]"


# ===================================================================
# H — Postreceive B sees A's output
# ===================================================================

class TestH_PostreceiveChaining:
    """Postreceive B receives A's modified ExecutionResult."""

    def test_post_chain(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
        plugins_dir = tmp_path / "plugins"
        _write_plugin(
            plugins_dir / "aa",
            "aa",
            '"postreceive"',
            """\
            class Plugin:
                def postreceive(self, result, ctx):
                    result.finish_reason = "aa-was-here"
                    return result
            """,
        )
        _write_plugin(
            plugins_dir / "bb",
            "bb",
            '"postreceive"',
            """\
            class Plugin:
                def postreceive(self, result, ctx):
                    if result.finish_reason == "aa-was-here":
                        result.text = result.text + " [BB-SAW-AA]"
                    return result
            """,
        )
        result = execute_with_plugins(
            service=_service(),
            backend="claude",
            compiled_prompt="test",
            temperature=0.7,
            max_output_tokens=4096,
            client=_mock_client(),
            plugins_dir=plugins_dir,
        )
        assert result.finish_reason == "aa-was-here"
        assert "[BB-SAW-AA]" in result.text


# ===================================================================
# I — Failing presend → disabled, send continues with original prompt
# ===================================================================

class TestI_PresendCrash:
    """Crashing presend plugin disabled; backend uses original prompt."""

    def test_presend_crash_continues(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
        plugins_dir = tmp_path / "plugins"
        _write_plugin(
            plugins_dir / "crasher",
            "crasher",
            '"presend"',
            """\
            class Plugin:
                def presend(self, prompt, ctx):
                    raise RuntimeError("boom")
            """,
        )
        result = execute_with_plugins(
            service=_service(),
            backend="claude",
            compiled_prompt="original prompt",
            temperature=0.7,
            max_output_tokens=4096,
            client=_mock_client(),
            plugins_dir=plugins_dir,
        )
        assert result.text == "Hello from Claude"


# ===================================================================
# J — Failing postreceive → last good ExecutionResult preserved
# ===================================================================

class TestJ_PostreceiveCrash:
    """Crashing postreceive plugin disabled; ExecutionResult unchanged."""

    def test_postreceive_crash_continues(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
        plugins_dir = tmp_path / "plugins"
        _write_plugin(
            plugins_dir / "crasher",
            "crasher",
            '"postreceive"',
            """\
            class Plugin:
                def postreceive(self, result, ctx):
                    raise ValueError("oops")
            """,
        )
        result = execute_with_plugins(
            service=_service(),
            backend="claude",
            compiled_prompt="test",
            temperature=0.7,
            max_output_tokens=4096,
            client=_mock_client(),
            plugins_dir=plugins_dir,
        )
        assert result.text == "Hello from Claude"
        assert result.backend == "claude"


# ===================================================================
# K — None from presend → treated as failure
# ===================================================================

class TestK_PresendNone:
    """Presend returning None → original prompt used for backend."""

    def test_none_presend(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
        plugins_dir = tmp_path / "plugins"
        _write_plugin(
            plugins_dir / "noner",
            "noner",
            '"presend"',
            """\
            class Plugin:
                def presend(self, prompt, ctx):
                    return None
            """,
        )
        captured: list[dict] = []

        def handler(request: httpx.Request) -> httpx.Response:
            captured.append(json.loads(request.content))
            return httpx.Response(200, json=CLAUDE_OK_BODY)

        client = httpx.Client(transport=httpx.MockTransport(handler))

        execute_with_plugins(
            service=_service(),
            backend="claude",
            compiled_prompt="original prompt",
            temperature=0.7,
            max_output_tokens=4096,
            client=client,
            plugins_dir=plugins_dir,
        )
        assert "original prompt" in captured[0]["system"]


# ===================================================================
# L — None from postreceive → treated as failure
# ===================================================================

class TestL_PostreceiveNone:
    """Postreceive returning None → ExecutionResult preserved."""

    def test_none_postreceive(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
        plugins_dir = tmp_path / "plugins"
        _write_plugin(
            plugins_dir / "noner",
            "noner",
            '"postreceive"',
            """\
            class Plugin:
                def postreceive(self, result, ctx):
                    return None
            """,
        )
        result = execute_with_plugins(
            service=_service(),
            backend="claude",
            compiled_prompt="test",
            temperature=0.7,
            max_output_tokens=4096,
            client=_mock_client(),
            plugins_dir=plugins_dir,
        )
        assert result.text == "Hello from Claude"


# ===================================================================
# M — One plugin failing doesn't disable healthy plugins
# ===================================================================

class TestM_HealthyPluginsSurvive:
    """Crashing plugin B doesn't disable plugins A or C."""

    def test_healthy_survive(self, tmp_path: Path) -> None:
        plugins_dir = tmp_path / "plugins"
        _write_plugin(
            plugins_dir / "aa-good",
            "aa-good",
            '"presend"',
            """\
            class Plugin:
                def presend(self, prompt, ctx):
                    return prompt + " >A"
            """,
        )
        _write_plugin(
            plugins_dir / "bb-bad",
            "bb-bad",
            '"presend"',
            """\
            class Plugin:
                def presend(self, prompt, ctx):
                    raise RuntimeError("crash")
            """,
        )
        _write_plugin(
            plugins_dir / "cc-good",
            "cc-good",
            '"presend"',
            """\
            class Plugin:
                def presend(self, prompt, ctx):
                    return prompt + " >C"
            """,
        )
        runner = build_plugin_runner(plugins_dir)
        out = runner.run_hook("presend", "start")
        assert out == "start >A >C"


# ===================================================================
# N — Next backend invocation starts fresh
# ===================================================================

class TestN_FreshInvocation:
    """Each execute_with_plugins call creates a fresh runner."""

    def test_fresh_per_invocation(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
        plugins_dir = tmp_path / "plugins"
        _write_plugin(
            plugins_dir / "marker",
            "marker",
            '"postreceive"',
            """\
            class Plugin:
                def postreceive(self, result, ctx):
                    result.text = result.text + " [PLUGIN]"
                    return result
            """,
        )
        client = _mock_client()

        r1 = execute_with_plugins(
            service=_service(), backend="claude",
            compiled_prompt="test", temperature=0.7,
            max_output_tokens=4096, client=client,
            plugins_dir=plugins_dir,
        )
        r2 = execute_with_plugins(
            service=_service(), backend="claude",
            compiled_prompt="test", temperature=0.7,
            max_output_tokens=4096, client=client,
            plugins_dir=plugins_dir,
        )
        assert "[PLUGIN]" in r1.text
        assert "[PLUGIN]" in r2.text


# ===================================================================
# O — End-to-end proof through real backend seam
# ===================================================================

class TestO_EndToEnd:
    """Real backend pipeline shows plugin effect."""

    def test_real_end_to_end(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
        plugins_dir = tmp_path / "plugins"
        _write_plugin(
            plugins_dir / "dual",
            "dual",
            '"presend", "postreceive"',
            """\
            class Plugin:
                def presend(self, prompt, ctx):
                    return "INJECTED PROMPT"

                def postreceive(self, result, ctx):
                    result.text = result.text + " [POST-PROCESSED]"
                    return result
            """,
        )
        captured: list[dict] = []

        def handler(request: httpx.Request) -> httpx.Response:
            captured.append(json.loads(request.content))
            return httpx.Response(200, json=CLAUDE_OK_BODY)

        client = httpx.Client(transport=httpx.MockTransport(handler))

        result = execute_with_plugins(
            service=_service(),
            backend="claude",
            compiled_prompt="original",
            temperature=0.7,
            max_output_tokens=4096,
            client=client,
            plugins_dir=plugins_dir,
        )

        assert "INJECTED PROMPT" in captured[0]["system"]
        assert result.text == "Hello from Claude [POST-PROCESSED]"

        empty = tmp_path / "empty"
        empty.mkdir()
        captured.clear()

        result_no_plugin = execute_with_plugins(
            service=_service(),
            backend="claude",
            compiled_prompt="original",
            temperature=0.7,
            max_output_tokens=4096,
            client=client,
            plugins_dir=empty,
        )
        assert "INJECTED PROMPT" not in captured[0]["system"]
        assert result_no_plugin.text == "Hello from Claude"


# ===================================================================
# P — Regression: existing backend behavior unchanged
# ===================================================================

class TestP_Regression:
    """execute_with_plugins with no plugins matches execute_full() exactly."""

    def test_field_identical(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
        empty = tmp_path / "empty"
        empty.mkdir()
        client = _mock_client()
        service = _service()

        with_wrapper = execute_with_plugins(
            service=service,
            backend="claude",
            compiled_prompt="regression test",
            temperature=0.7,
            max_output_tokens=4096,
            client=client,
            plugins_dir=empty,
        )
        baseline = service.execute_full(
            backend="claude",
            compiled_prompt="regression test",
            temperature=0.7,
            max_output_tokens=4096,
            client=client,
        )
        assert with_wrapper.text == baseline.text
        assert with_wrapper.backend == baseline.backend
        assert with_wrapper.finish_reason == baseline.finish_reason
        assert with_wrapper.usage_input_tokens == baseline.usage_input_tokens
        assert with_wrapper.usage_output_tokens == baseline.usage_output_tokens


# ===================================================================
# Q — ExecutionResult type/shape integrity after postreceive
# ===================================================================

class TestQ_ResultIntegrity:
    """ExecutionResult preserves type and fields after postreceive use."""

    def test_type_preserved(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
        plugins_dir = tmp_path / "plugins"
        _write_plugin(
            plugins_dir / "modifier",
            "modifier",
            '"postreceive"',
            """\
            class Plugin:
                def postreceive(self, result, ctx):
                    result.text = result.text + " [MODIFIED]"
                    return result
            """,
        )
        result = execute_with_plugins(
            service=_service(),
            backend="claude",
            compiled_prompt="test",
            temperature=0.7,
            max_output_tokens=4096,
            client=_mock_client(),
            plugins_dir=plugins_dir,
        )
        assert isinstance(result, ExecutionResult)
        assert isinstance(result.text, str)
        assert isinstance(result.backend, str)
        assert "[MODIFIED]" in result.text


# ===================================================================
# R — Streaming path: presend applies to streaming execution
# ===================================================================

class TestR_StreamPresend:
    """Presend hook applies to streaming execute path."""

    def test_stream_presend(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
        plugins_dir = tmp_path / "plugins"

        captured: list[dict] = []

        def handler(request: httpx.Request) -> httpx.Response:
            captured.append(json.loads(request.content))
            sse_data = (
                'event: message_start\ndata: {"type":"message_start"}\n\n'
                'event: content_block_delta\ndata: {"type":"content_block_delta","delta":{"type":"text_delta","text":"streamed"}}\n\n'
                'event: message_delta\ndata: {"type":"message_delta","delta":{"stop_reason":"end_turn"}}\n\n'
            )
            return httpx.Response(
                200,
                content=sse_data.encode(),
                headers={"content-type": "text/event-stream"},
            )

        client = httpx.Client(transport=httpx.MockTransport(handler))

        _write_plugin(
            plugins_dir / "injector",
            "injector",
            '"presend"',
            """\
            class Plugin:
                def presend(self, prompt, ctx):
                    return "STREAM INJECTED"
            """,
        )
        events = list(execute_stream_with_plugins(
            service=_service(),
            backend="claude",
            compiled_prompt="original",
            temperature=0.7,
            max_output_tokens=4096,
            client=client,
            plugins_dir=plugins_dir,
        ))
        assert len(captured) == 1
        assert "STREAM INJECTED" in captured[0]["system"]
        assert any(e.text == "streamed" for e in events)
