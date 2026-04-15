"""Tests for the GPT adapter."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

import pytest

from interceptor.adapters.gpt import DEFAULT_MODEL, GptAdapter
from interceptor.adapters.models import AdaptedRequest, BackendName, StreamEvent


class TestGptAdapt:
    def test_backend_name(self) -> None:
        adapter = GptAdapter()
        assert adapter.backend_name == BackendName.GPT

    def test_adapt_returns_adapted_request(self) -> None:
        adapter = GptAdapter()
        req = adapter.adapt(
            compiled_prompt="Test prompt",
            temperature=0.7,
            max_output_tokens=4096,
            stream=False,
        )
        assert isinstance(req, AdaptedRequest)
        assert req.backend == BackendName.GPT

    def test_adapt_payload_shape(self) -> None:
        adapter = GptAdapter()
        req = adapter.adapt(
            compiled_prompt="Test prompt",
            temperature=1.0,
            max_output_tokens=2048,
            stream=True,
        )
        payload = req.payload
        assert payload["model"] == DEFAULT_MODEL
        assert isinstance(payload["messages"], list)
        assert payload["messages"][0]["role"] == "system"
        assert payload["messages"][1]["role"] == "user"
        assert payload["max_tokens"] == 2048
        assert payload["temperature"] == 1.0
        assert payload["stream"] is True

    def test_adapt_preserves_max_output_tokens(self) -> None:
        adapter = GptAdapter()
        req = adapter.adapt(
            compiled_prompt="x",
            temperature=0.5,
            max_output_tokens=512,
            stream=False,
        )
        assert req.max_output_tokens == 512


class TestGptSend:
    def test_no_api_key_raises(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        adapter = GptAdapter()
        req = adapter.adapt(
            compiled_prompt="x",
            temperature=0.7,
            max_output_tokens=1024,
            stream=False,
        )
        from interceptor.adapters.errors import MissingApiKeyError

        with pytest.raises(MissingApiKeyError, match="OPENAI_API_KEY"):
            adapter.send(req)

    def test_send_with_mock_transport(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("OPENAI_API_KEY", "test-key")
        import httpx

        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                200,
                json={
                    "choices": [
                        {"message": {"content": "hello from gpt"}, "finish_reason": "stop"}
                    ],
                    "usage": {"prompt_tokens": 10, "completion_tokens": 5},
                },
            )

        client = httpx.Client(transport=httpx.MockTransport(handler))
        adapter = GptAdapter()
        req = adapter.adapt(
            compiled_prompt="x",
            temperature=0.7,
            max_output_tokens=1024,
            stream=False,
        )
        result = adapter.send(req, client=client)
        assert result == "hello from gpt"


class TestGptStream:
    def test_no_client_raises(self) -> None:
        adapter = GptAdapter()
        req = adapter.adapt(
            compiled_prompt="x",
            temperature=0.7,
            max_output_tokens=1024,
            stream=True,
        )
        with pytest.raises(RuntimeError, match="requires a client"):
            list(adapter.stream(req))

    def test_stream_with_mock_client(self) -> None:
        adapter = GptAdapter()
        req = adapter.adapt(
            compiled_prompt="x",
            temperature=0.7,
            max_output_tokens=1024,
            stream=True,
        )

        @dataclass
        class MockStreamClient:
            def stream(self, request: AdaptedRequest) -> Iterable[StreamEvent]:
                yield StreamEvent(type="content", text="part1")
                yield StreamEvent(type="done", done=True)

        events = list(adapter.stream(req, client=MockStreamClient()))
        assert len(events) == 2
        assert events[0].text == "part1"
        assert events[-1].done is True

    def test_stream_invalid_client_raises(self) -> None:
        adapter = GptAdapter()
        req = adapter.adapt(
            compiled_prompt="x",
            temperature=0.7,
            max_output_tokens=1024,
            stream=True,
        )
        with pytest.raises(TypeError, match="must implement stream"):
            list(adapter.stream(req, client=object()))
