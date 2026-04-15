"""Tests for the AdapterService orchestration layer."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

import pytest

from interceptor.adapters.models import AdaptedRequest, BackendName, StreamEvent
from interceptor.adapters.service import AdapterService


class TestAdaptRequest:
    def test_adapt_claude(self) -> None:
        svc = AdapterService()
        req = svc.adapt_request(
            backend="claude",
            compiled_prompt="test",
            temperature=0.5,
            max_output_tokens=4096,
        )
        assert req.backend == BackendName.CLAUDE
        assert req.streaming is False

    def test_adapt_gpt(self) -> None:
        svc = AdapterService()
        req = svc.adapt_request(
            backend="gpt",
            compiled_prompt="test",
            temperature=1.0,
            max_output_tokens=2048,
            stream=True,
        )
        assert req.backend == BackendName.GPT
        assert req.streaming is True

    def test_unknown_backend_raises(self) -> None:
        svc = AdapterService()
        with pytest.raises(ValueError, match="Unknown backend"):
            svc.adapt_request(
                backend="llama",
                compiled_prompt="test",
                temperature=0.7,
                max_output_tokens=1024,
            )


class TestExecute:
    def test_execute_send_mode(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
        import httpx

        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                200,
                json={
                    "content": [{"type": "text", "text": "sync result"}],
                    "stop_reason": "end_turn",
                    "usage": {"input_tokens": 10, "output_tokens": 5},
                },
            )

        client = httpx.Client(transport=httpx.MockTransport(handler))
        svc = AdapterService()
        result = svc.execute(
            backend="claude",
            compiled_prompt="test",
            temperature=0.7,
            max_output_tokens=1024,
            stream=False,
            client=client,
        )
        assert result == "sync result"

    def test_execute_stream_mode(self) -> None:
        svc = AdapterService()

        @dataclass
        class MockStreamClient:
            def stream(self, request: AdaptedRequest) -> Iterable[StreamEvent]:
                yield StreamEvent(type="content", text="chunk")
                yield StreamEvent(type="done", done=True)

        iterable = svc.execute(
            backend="gpt",
            compiled_prompt="test",
            temperature=0.7,
            max_output_tokens=1024,
            stream=True,
            client=MockStreamClient(),
        )
        events = list(iterable)  # type: ignore[arg-type]
        assert len(events) == 2
        assert events[-1].done is True

    def test_execute_no_api_key_raises(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        from interceptor.adapters.errors import MissingApiKeyError

        svc = AdapterService()
        with pytest.raises(MissingApiKeyError):
            svc.execute(
                backend="claude",
                compiled_prompt="test",
                temperature=0.7,
                max_output_tokens=1024,
                stream=False,
            )
