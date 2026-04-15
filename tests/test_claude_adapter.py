"""Tests for the Claude adapter."""

from __future__ import annotations

import pytest

from interceptor.adapters.claude import ClaudeAdapter, DEFAULT_MODEL
from interceptor.adapters.models import AdaptedRequest, BackendName, StreamEvent


class TestClaudeAdapt:
    def test_backend_name(self) -> None:
        adapter = ClaudeAdapter()
        assert adapter.backend_name == BackendName.CLAUDE

    def test_adapt_returns_adapted_request(self) -> None:
        adapter = ClaudeAdapter()
        req = adapter.adapt(
            compiled_prompt="Test prompt",
            temperature=0.5,
            max_output_tokens=4096,
            stream=False,
        )
        assert isinstance(req, AdaptedRequest)
        assert req.backend == BackendName.CLAUDE

    def test_adapt_payload_shape(self) -> None:
        adapter = ClaudeAdapter()
        req = adapter.adapt(
            compiled_prompt="Test prompt",
            temperature=0.8,
            max_output_tokens=2048,
            stream=True,
        )
        payload = req.payload
        assert payload["model"] == DEFAULT_MODEL
        assert "system" in payload
        assert isinstance(payload["messages"], list)
        assert payload["messages"][0]["role"] == "user"
        assert payload["max_tokens"] == 2048
        assert payload["temperature"] == 0.8
        assert payload["stream"] is True

    def test_adapt_preserves_temperature(self) -> None:
        adapter = ClaudeAdapter()
        req = adapter.adapt(
            compiled_prompt="x",
            temperature=0.3,
            max_output_tokens=1024,
            stream=False,
        )
        assert req.temperature == 0.3


class TestClaudeSend:
    def test_no_api_key_raises(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        adapter = ClaudeAdapter()
        req = adapter.adapt(
            compiled_prompt="x",
            temperature=0.7,
            max_output_tokens=1024,
            stream=False,
        )
        from interceptor.adapters.errors import MissingApiKeyError

        with pytest.raises(MissingApiKeyError, match="ANTHROPIC_API_KEY"):
            adapter.send(req)

    def test_send_with_mock_transport(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
        import httpx

        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                200,
                json={
                    "content": [{"type": "text", "text": "hello from claude"}],
                    "stop_reason": "end_turn",
                    "usage": {"input_tokens": 10, "output_tokens": 5},
                },
            )

        client = httpx.Client(transport=httpx.MockTransport(handler))
        adapter = ClaudeAdapter()
        req = adapter.adapt(
            compiled_prompt="x",
            temperature=0.7,
            max_output_tokens=1024,
            stream=False,
        )
        result = adapter.send(req, client=client)
        assert result == "hello from claude"


class TestClaudeStream:
    def test_no_api_key_raises(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        adapter = ClaudeAdapter()
        req = adapter.adapt(
            compiled_prompt="x",
            temperature=0.7,
            max_output_tokens=1024,
            stream=True,
        )
        from interceptor.adapters.errors import MissingApiKeyError

        with pytest.raises(MissingApiKeyError, match="ANTHROPIC_API_KEY"):
            list(adapter.stream(req))

    def test_stream_with_mock_transport(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
        import json

        import httpx

        sse_lines = [
            'event: content_block_delta',
            'data: ' + json.dumps({"type": "content_block_delta", "index": 0, "delta": {"type": "text_delta", "text": "hello "}}),
            '',
            'event: content_block_delta',
            'data: ' + json.dumps({"type": "content_block_delta", "index": 0, "delta": {"type": "text_delta", "text": "world"}}),
            '',
            'event: message_delta',
            'data: ' + json.dumps({"type": "message_delta", "delta": {"stop_reason": "end_turn"}, "usage": {"output_tokens": 5}}),
            '',
        ]
        body = "\n".join(sse_lines).encode()

        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, content=body, headers={"content-type": "text/event-stream"})

        client = httpx.Client(transport=httpx.MockTransport(handler))
        adapter = ClaudeAdapter()
        req = adapter.adapt(
            compiled_prompt="x",
            temperature=0.7,
            max_output_tokens=1024,
            stream=True,
        )
        events = list(adapter.stream(req, client=client))
        assert len(events) == 3
        assert events[0].text == "hello "
        assert events[1].text == "world"
        assert events[-1].done is True
