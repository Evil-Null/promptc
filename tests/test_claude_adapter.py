"""Tests for the Claude adapter."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

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
    def test_no_client_raises(self) -> None:
        adapter = ClaudeAdapter()
        req = adapter.adapt(
            compiled_prompt="x",
            temperature=0.7,
            max_output_tokens=1024,
            stream=False,
        )
        with pytest.raises(RuntimeError, match="requires a client"):
            adapter.send(req)

    def test_send_with_mock_client(self) -> None:
        adapter = ClaudeAdapter()
        req = adapter.adapt(
            compiled_prompt="x",
            temperature=0.7,
            max_output_tokens=1024,
            stream=False,
        )

        @dataclass
        class MockClient:
            def send(self, request: AdaptedRequest) -> str:
                return "mock response"

        result = adapter.send(req, client=MockClient())
        assert result == "mock response"

    def test_send_invalid_client_raises(self) -> None:
        adapter = ClaudeAdapter()
        req = adapter.adapt(
            compiled_prompt="x",
            temperature=0.7,
            max_output_tokens=1024,
            stream=False,
        )
        with pytest.raises(TypeError, match="must implement send"):
            adapter.send(req, client=object())


class TestClaudeStream:
    def test_no_client_raises(self) -> None:
        adapter = ClaudeAdapter()
        req = adapter.adapt(
            compiled_prompt="x",
            temperature=0.7,
            max_output_tokens=1024,
            stream=True,
        )
        with pytest.raises(RuntimeError, match="requires a client"):
            list(adapter.stream(req))

    def test_stream_with_mock_client(self) -> None:
        adapter = ClaudeAdapter()
        req = adapter.adapt(
            compiled_prompt="x",
            temperature=0.7,
            max_output_tokens=1024,
            stream=True,
        )

        @dataclass
        class MockStreamClient:
            def stream(self, request: AdaptedRequest) -> Iterable[StreamEvent]:
                yield StreamEvent(type="content", text="hello ")
                yield StreamEvent(type="content", text="world")
                yield StreamEvent(type="done", done=True)

        events = list(adapter.stream(req, client=MockStreamClient()))
        assert len(events) == 3
        assert events[-1].done is True

    def test_stream_invalid_client_raises(self) -> None:
        adapter = ClaudeAdapter()
        req = adapter.adapt(
            compiled_prompt="x",
            temperature=0.7,
            max_output_tokens=1024,
            stream=True,
        )
        with pytest.raises(TypeError, match="must implement stream"):
            list(adapter.stream(req, client=object()))
