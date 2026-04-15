"""PR-10 tests — real streaming passthrough via httpx SSE, all mocked."""

from __future__ import annotations

import json

import httpx
import pytest

from interceptor.adapters.errors import (
    BackendRequestError,
    BackendResponseParseError,
    MissingApiKeyError,
)
from interceptor.adapters.models import StreamEvent
from interceptor.adapters.transport import stream_claude, stream_gpt


# ---------------------------------------------------------------------------
# SSE helpers
# ---------------------------------------------------------------------------


def _claude_sse(chunks: list[str], *, stop_reason: str = "end_turn") -> bytes:
    lines: list[str] = []
    lines.append("event: message_start")
    lines.append(
        'data: ' + json.dumps({"type": "message_start", "message": {"id": "msg_test"}})
    )
    lines.append("")
    for chunk in chunks:
        lines.append("event: content_block_delta")
        lines.append(
            'data: ' + json.dumps({
                "type": "content_block_delta",
                "index": 0,
                "delta": {"type": "text_delta", "text": chunk},
            })
        )
        lines.append("")
    lines.append("event: message_delta")
    lines.append(
        'data: ' + json.dumps({
            "type": "message_delta",
            "delta": {"stop_reason": stop_reason},
            "usage": {"output_tokens": 10},
        })
    )
    lines.append("")
    lines.append("event: message_stop")
    lines.append('data: ' + json.dumps({"type": "message_stop"}))
    lines.append("")
    return "\n".join(lines).encode()


def _gpt_sse(chunks: list[str]) -> bytes:
    lines: list[str] = []
    for chunk in chunks:
        lines.append(
            'data: ' + json.dumps({
                "choices": [{"delta": {"content": chunk}, "finish_reason": None}]
            })
        )
        lines.append("")
    lines.append("data: [DONE]")
    lines.append("")
    return "\n".join(lines).encode()


def _stream_client(body: bytes, status: int = 200) -> httpx.Client:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            status, content=body, headers={"content-type": "text/event-stream"}
        )

    return httpx.Client(transport=httpx.MockTransport(handler))


# ===========================================================================
# A: Protocol declares required methods
# ===========================================================================


class TestProtocol:
    def test_protocol_declares_send_full(self) -> None:
        from interceptor.adapters.base import BackendAdapter

        assert hasattr(BackendAdapter, "send_full")

    def test_protocol_declares_stream(self) -> None:
        from interceptor.adapters.base import BackendAdapter

        assert hasattr(BackendAdapter, "stream")

    def test_protocol_declares_send(self) -> None:
        from interceptor.adapters.base import BackendAdapter

        assert hasattr(BackendAdapter, "send")


# ===========================================================================
# B: Claude streaming success
# ===========================================================================


class TestClaudeStreamSuccess:
    def test_single_chunk(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
        client = _stream_client(_claude_sse(["Hello"]))
        events = list(stream_claude({"messages": []}, client=client))
        content_events = [e for e in events if e.type == "content"]
        done_events = [e for e in events if e.done]
        assert len(content_events) == 1
        assert content_events[0].text == "Hello"
        assert len(done_events) == 1

    def test_multiple_chunks(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
        client = _stream_client(_claude_sse(["Hello", " ", "world"]))
        events = list(stream_claude({"messages": []}, client=client))
        texts = [e.text for e in events if e.type == "content"]
        assert texts == ["Hello", " ", "world"]
        assert events[-1].done is True

    def test_payload_gets_stream_true(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
        captured: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response:
            captured.append(request)
            return httpx.Response(
                200, content=_claude_sse(["ok"]),
                headers={"content-type": "text/event-stream"},
            )

        client = httpx.Client(transport=httpx.MockTransport(handler))
        list(stream_claude({"messages": [], "stream": False}, client=client))
        sent_body = json.loads(captured[0].content)
        assert sent_body["stream"] is True

    def test_ignored_event_types(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
        sse = "\n".join([
            "event: message_start",
            'data: ' + json.dumps({"type": "message_start"}),
            "",
            "event: ping",
            'data: ' + json.dumps({"type": "ping"}),
            "",
            "event: content_block_start",
            'data: ' + json.dumps({"type": "content_block_start", "index": 0, "content_block": {"type": "text"}}),
            "",
            "event: content_block_delta",
            'data: ' + json.dumps({"type": "content_block_delta", "index": 0, "delta": {"type": "text_delta", "text": "hi"}}),
            "",
            "event: content_block_stop",
            'data: ' + json.dumps({"type": "content_block_stop", "index": 0}),
            "",
            "event: message_delta",
            'data: ' + json.dumps({"type": "message_delta", "delta": {"stop_reason": "end_turn"}, "usage": {"output_tokens": 1}}),
            "",
        ]).encode()
        client = _stream_client(sse)
        events = list(stream_claude({"messages": []}, client=client))
        content_events = [e for e in events if e.type == "content"]
        assert len(content_events) == 1
        assert content_events[0].text == "hi"

    def test_headers_correct(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-secret")
        captured: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response:
            captured.append(request)
            return httpx.Response(
                200, content=_claude_sse(["x"]),
                headers={"content-type": "text/event-stream"},
            )

        client = httpx.Client(transport=httpx.MockTransport(handler))
        list(stream_claude({"messages": []}, client=client))
        req = captured[0]
        assert req.headers["x-api-key"] == "sk-secret"
        assert req.headers["anthropic-version"] == "2023-06-01"


# ===========================================================================
# C: GPT streaming success
# ===========================================================================


class TestGptStreamSuccess:
    def test_single_chunk(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
        client = _stream_client(_gpt_sse(["Hello"]))
        events = list(stream_gpt({"messages": []}, client=client))
        content_events = [e for e in events if e.type == "content"]
        done_events = [e for e in events if e.done]
        assert len(content_events) == 1
        assert content_events[0].text == "Hello"
        assert len(done_events) == 1

    def test_multiple_chunks(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
        client = _stream_client(_gpt_sse(["part1", " part2", " part3"]))
        events = list(stream_gpt({"messages": []}, client=client))
        texts = [e.text for e in events if e.type == "content"]
        assert texts == ["part1", " part2", " part3"]
        assert events[-1].done is True

    def test_payload_gets_stream_true(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
        captured: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response:
            captured.append(request)
            return httpx.Response(
                200, content=_gpt_sse(["ok"]),
                headers={"content-type": "text/event-stream"},
            )

        client = httpx.Client(transport=httpx.MockTransport(handler))
        list(stream_gpt({"messages": [], "stream": False}, client=client))
        sent_body = json.loads(captured[0].content)
        assert sent_body["stream"] is True

    def test_done_event_terminates(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
        sse = "\n".join([
            'data: ' + json.dumps({"choices": [{"delta": {"content": "a"}, "finish_reason": None}]}),
            "",
            "data: [DONE]",
            "",
            'data: ' + json.dumps({"choices": [{"delta": {"content": "SHOULD NOT APPEAR"}, "finish_reason": None}]}),
            "",
        ]).encode()
        client = _stream_client(sse)
        events = list(stream_gpt({"messages": []}, client=client))
        texts = [e.text for e in events if e.type == "content"]
        assert texts == ["a"]
        assert events[-1].done is True

    def test_empty_delta_skipped(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
        sse = "\n".join([
            'data: ' + json.dumps({"choices": [{"delta": {"role": "assistant"}, "finish_reason": None}]}),
            "",
            'data: ' + json.dumps({"choices": [{"delta": {"content": "hi"}, "finish_reason": None}]}),
            "",
            'data: ' + json.dumps({"choices": [{"delta": {}, "finish_reason": "stop"}]}),
            "",
            "data: [DONE]",
            "",
        ]).encode()
        client = _stream_client(sse)
        events = list(stream_gpt({"messages": []}, client=client))
        content_events = [e for e in events if e.type == "content"]
        assert len(content_events) == 1
        assert content_events[0].text == "hi"

    def test_headers_correct(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("OPENAI_API_KEY", "sk-secret")
        captured: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response:
            captured.append(request)
            return httpx.Response(
                200, content=_gpt_sse(["x"]),
                headers={"content-type": "text/event-stream"},
            )

        client = httpx.Client(transport=httpx.MockTransport(handler))
        list(stream_gpt({"messages": []}, client=client))
        req = captured[0]
        assert req.headers["authorization"] == "Bearer sk-secret"


# ===========================================================================
# D: Stream parse failures
# ===========================================================================


class TestStreamParseFailures:
    def test_claude_malformed_json(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
        sse = "event: content_block_delta\ndata: {INVALID JSON}\n\n".encode()
        client = _stream_client(sse)
        with pytest.raises(BackendResponseParseError, match="claude"):
            list(stream_claude({"messages": []}, client=client))

    def test_gpt_malformed_json(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
        sse = "data: {INVALID JSON}\n\n".encode()
        client = _stream_client(sse)
        with pytest.raises(BackendResponseParseError, match="gpt"):
            list(stream_gpt({"messages": []}, client=client))

    def test_claude_http_error(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
        client = _stream_client(b'{"error": "rate limited"}', status=429)
        with pytest.raises(BackendRequestError) as exc_info:
            list(stream_claude({"messages": []}, client=client))
        assert exc_info.value.status_code == 429
        assert exc_info.value.backend == "claude"

    def test_gpt_http_error(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
        client = _stream_client(b'{"error": "unauthorized"}', status=401)
        with pytest.raises(BackendRequestError) as exc_info:
            list(stream_gpt({"messages": []}, client=client))
        assert exc_info.value.status_code == 401
        assert exc_info.value.backend == "gpt"

    def test_claude_missing_key(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        with pytest.raises(MissingApiKeyError, match="ANTHROPIC_API_KEY"):
            list(stream_claude({"messages": []}))

    def test_gpt_missing_key(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        with pytest.raises(MissingApiKeyError, match="OPENAI_API_KEY"):
            list(stream_gpt({"messages": []}))


# ===========================================================================
# E: Service execute_stream
# ===========================================================================


class TestServiceExecuteStream:
    def test_claude_stream(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
        from interceptor.adapters.service import AdapterService

        client = _stream_client(_claude_sse(["hello", " world"]))
        svc = AdapterService()
        events = list(
            svc.execute_stream(
                backend="claude",
                compiled_prompt="test input",
                temperature=0.7,
                max_output_tokens=2048,
                client=client,
            )
        )
        texts = [e.text for e in events if e.type == "content"]
        assert texts == ["hello", " world"]
        assert events[-1].done is True

    def test_gpt_stream(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
        from interceptor.adapters.service import AdapterService

        client = _stream_client(_gpt_sse(["part1", " part2"]))
        svc = AdapterService()
        events = list(
            svc.execute_stream(
                backend="gpt",
                compiled_prompt="test input",
                temperature=0.5,
                max_output_tokens=1024,
                client=client,
            )
        )
        texts = [e.text for e in events if e.type == "content"]
        assert texts == ["part1", " part2"]
        assert events[-1].done is True

    def test_unknown_backend_raises(self) -> None:
        from interceptor.adapters.service import AdapterService

        svc = AdapterService()
        with pytest.raises(ValueError, match="Unknown backend"):
            list(
                svc.execute_stream(
                    backend="llama",
                    compiled_prompt="test",
                    temperature=0.7,
                    max_output_tokens=1024,
                )
            )


# ===========================================================================
# F: CLI streaming integration
# ===========================================================================


class TestCliStreaming:
    def test_stream_and_json_rejected(self) -> None:
        from typer.testing import CliRunner

        from interceptor.cli import app

        runner = CliRunner()
        result = runner.invoke(
            app,
            ["run", "test", "--template", "explain", "--backend", "claude",
             "--stream", "--json"],
        )
        assert result.exit_code != 0
        assert "--stream" in result.output or "--json" in result.output

    def test_dry_run_with_stream_shows_dry_run(self) -> None:
        from typer.testing import CliRunner

        from interceptor.cli import app

        runner = CliRunner()
        result = runner.invoke(
            app,
            ["run", "test input", "--template", "explain", "--backend", "claude",
             "--dry-run", "--stream"],
        )
        assert result.exit_code == 0
        assert "Dry-run" in result.output

    def test_stream_success_path(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
        from unittest.mock import patch

        from typer.testing import CliRunner

        from interceptor.cli import app

        sse_body = _claude_sse(["Hello", " from", " stream"])

        def mock_stream(
            method: str, url: str, *, headers: dict, json: dict, **kwargs: object
        ):
            import contextlib

            resp = httpx.Response(
                200, content=sse_body,
                headers={"content-type": "text/event-stream"},
            )

            @contextlib.contextmanager
            def ctx():
                yield resp

            return ctx()

        with patch(
            "interceptor.adapters.transport.httpx.Client"
        ) as mock_client_cls:
            mock_instance = mock_client_cls.return_value
            mock_instance.stream = mock_stream
            mock_instance.close = lambda: None

            runner = CliRunner()
            result = runner.invoke(
                app,
                ["run", "test input", "--template", "explain", "--backend", "claude",
                 "--stream"],
            )

        assert result.exit_code == 0
        assert "Hello from stream" in result.output

    def test_stream_failure_exits_nonzero(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        from typer.testing import CliRunner

        from interceptor.cli import app

        runner = CliRunner()
        result = runner.invoke(
            app,
            ["run", "test input", "--template", "explain", "--backend", "claude",
             "--stream"],
        )
        assert result.exit_code != 0


# ===========================================================================
# G: Regression safety — non-streaming still works
# ===========================================================================


class TestRegressionSafety:
    def test_non_streaming_send_still_works(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
        from interceptor.adapters.transport import send_claude

        body = {
            "content": [{"type": "text", "text": "buffered response"}],
            "stop_reason": "end_turn",
            "usage": {"input_tokens": 10, "output_tokens": 5},
        }

        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json=body)

        client = httpx.Client(transport=httpx.MockTransport(handler))
        result = send_claude({"messages": []}, client=client)
        assert result.text == "buffered response"
        assert result.backend == "claude"

    def test_dry_run_unchanged(self) -> None:
        from typer.testing import CliRunner

        from interceptor.cli import app

        runner = CliRunner()
        result = runner.invoke(
            app,
            ["run", "explain async", "--template", "explain", "--backend", "gpt",
             "--dry-run"],
        )
        assert result.exit_code == 0
        assert "Dry-run" in result.output

    def test_stream_event_model_unchanged(self) -> None:
        e = StreamEvent(type="content", text="hi")
        assert e.done is False
        assert e.text == "hi"

        e2 = StreamEvent(type="done", done=True)
        assert e2.done is True
        assert e2.text == ""
