"""PR-9 tests — real SEND path via httpx, all mocked."""

from __future__ import annotations

import json

import httpx
import pytest

from interceptor.adapters.errors import (
    BackendRequestError,
    BackendResponseParseError,
    MissingApiKeyError,
)
from interceptor.adapters.models import ExecutionResult
from interceptor.adapters.transport import send_claude, send_gpt


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

CLAUDE_OK_BODY = {
    "content": [{"type": "text", "text": "Hello from Claude"}],
    "stop_reason": "end_turn",
    "usage": {"input_tokens": 15, "output_tokens": 8},
}

GPT_OK_BODY = {
    "choices": [
        {"message": {"content": "Hello from GPT"}, "finish_reason": "stop"}
    ],
    "usage": {"prompt_tokens": 12, "completion_tokens": 6},
}


def _make_client(body: dict, status: int = 200) -> httpx.Client:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status, json=body)

    return httpx.Client(transport=httpx.MockTransport(handler))


# ===========================================================================
# A: Claude send success
# ===========================================================================

class TestClaudeSendSuccess:
    def test_returns_execution_result(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
        result = send_claude(
            {"model": "claude-sonnet-4-20250514", "messages": []},
            client=_make_client(CLAUDE_OK_BODY),
        )
        assert isinstance(result, ExecutionResult)
        assert result.backend == "claude"
        assert result.text == "Hello from Claude"
        assert result.finish_reason == "end_turn"
        assert result.usage_input_tokens == 15
        assert result.usage_output_tokens == 8

    def test_multi_content_blocks(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
        body = {
            "content": [
                {"type": "text", "text": "Part A"},
                {"type": "text", "text": " Part B"},
            ],
            "stop_reason": "end_turn",
            "usage": {"input_tokens": 5, "output_tokens": 4},
        }
        result = send_claude({"messages": []}, client=_make_client(body))
        assert result.text == "Part A Part B"

    def test_payload_gets_stream_false(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
        captured: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response:
            captured.append(request)
            return httpx.Response(200, json=CLAUDE_OK_BODY)

        client = httpx.Client(transport=httpx.MockTransport(handler))
        send_claude({"messages": [], "stream": True}, client=client)
        sent_body = json.loads(captured[0].content)
        assert sent_body["stream"] is False


# ===========================================================================
# B: GPT send success
# ===========================================================================

class TestGptSendSuccess:
    def test_returns_execution_result(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
        result = send_gpt(
            {"model": "gpt-4o", "messages": []},
            client=_make_client(GPT_OK_BODY),
        )
        assert isinstance(result, ExecutionResult)
        assert result.backend == "gpt"
        assert result.text == "Hello from GPT"
        assert result.finish_reason == "stop"
        assert result.usage_input_tokens == 12
        assert result.usage_output_tokens == 6

    def test_payload_gets_stream_false(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
        captured: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response:
            captured.append(request)
            return httpx.Response(200, json=GPT_OK_BODY)

        client = httpx.Client(transport=httpx.MockTransport(handler))
        send_gpt({"messages": [], "stream": True}, client=client)
        sent_body = json.loads(captured[0].content)
        assert sent_body["stream"] is False


# ===========================================================================
# C: Missing API key errors
# ===========================================================================

class TestMissingApiKey:
    def test_claude_missing_key(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        with pytest.raises(MissingApiKeyError, match="ANTHROPIC_API_KEY"):
            send_claude({"messages": []})

    def test_gpt_missing_key(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        with pytest.raises(MissingApiKeyError, match="OPENAI_API_KEY"):
            send_gpt({"messages": []})

    def test_error_attributes(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        with pytest.raises(MissingApiKeyError) as exc_info:
            send_claude({"messages": []})
        assert exc_info.value.env_var == "ANTHROPIC_API_KEY"
        assert exc_info.value.backend == "claude"


# ===========================================================================
# D: HTTP and response parse failures
# ===========================================================================

class TestBackendErrors:
    def test_claude_http_error(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
        client = _make_client({"error": {"message": "rate limited"}}, status=429)
        with pytest.raises(BackendRequestError) as exc_info:
            send_claude({"messages": []}, client=client)
        assert exc_info.value.status_code == 429
        assert exc_info.value.backend == "claude"

    def test_gpt_http_error(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
        client = _make_client({"error": "unauthorized"}, status=401)
        with pytest.raises(BackendRequestError) as exc_info:
            send_gpt({"messages": []}, client=client)
        assert exc_info.value.status_code == 401
        assert exc_info.value.backend == "gpt"

    def test_claude_parse_error_missing_content(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
        client = _make_client({"wrong_key": "value"})
        with pytest.raises(BackendResponseParseError, match="claude"):
            send_claude({"messages": []}, client=client)

    def test_gpt_parse_error_missing_choices(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
        client = _make_client({"wrong_key": "value"})
        with pytest.raises(BackendResponseParseError, match="gpt"):
            send_gpt({"messages": []}, client=client)

    def test_claude_parse_error_no_text_blocks(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
        body = {"content": [{"type": "image", "source": {}}], "stop_reason": "end_turn", "usage": {}}
        result = send_claude({"messages": []}, client=_make_client(body))
        assert result.text == ""

    def test_gpt_parse_error_empty_choices(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
        client = _make_client({"choices": []})
        with pytest.raises(BackendResponseParseError, match="gpt"):
            send_gpt({"messages": []}, client=client)


# ===========================================================================
# E: AdapterService.execute_full integration
# ===========================================================================

class TestServiceExecuteFull:
    def test_claude_execute_full(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
        from interceptor.adapters.service import AdapterService

        client = _make_client(CLAUDE_OK_BODY)
        svc = AdapterService()
        result = svc.execute_full(
            backend="claude",
            compiled_prompt="test input",
            temperature=0.7,
            max_output_tokens=2048,
            client=client,
        )
        assert isinstance(result, ExecutionResult)
        assert result.backend == "claude"
        assert result.text == "Hello from Claude"

    def test_gpt_execute_full(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
        from interceptor.adapters.service import AdapterService

        client = _make_client(GPT_OK_BODY)
        svc = AdapterService()
        result = svc.execute_full(
            backend="gpt",
            compiled_prompt="test input",
            temperature=0.5,
            max_output_tokens=1024,
            client=client,
        )
        assert isinstance(result, ExecutionResult)
        assert result.backend == "gpt"
        assert result.text == "Hello from GPT"


# ===========================================================================
# F: ExecutionResult model
# ===========================================================================

class TestExecutionResultModel:
    def test_default_none_fields(self) -> None:
        r = ExecutionResult(backend="test", text="hi")
        assert r.finish_reason is None
        assert r.usage_input_tokens is None
        assert r.usage_output_tokens is None

    def test_all_fields_set(self) -> None:
        r = ExecutionResult(
            backend="claude",
            text="hello",
            finish_reason="end_turn",
            usage_input_tokens=100,
            usage_output_tokens=50,
        )
        assert r.backend == "claude"
        assert r.text == "hello"
        assert r.finish_reason == "end_turn"
        assert r.usage_input_tokens == 100
        assert r.usage_output_tokens == 50


# ===========================================================================
# G: Error model attributes
# ===========================================================================

class TestErrorModels:
    def test_missing_api_key_str(self) -> None:
        err = MissingApiKeyError("MY_KEY", "test-backend")
        assert "MY_KEY" in str(err)
        assert "test-backend" in str(err)

    def test_backend_request_error_str(self) -> None:
        err = BackendRequestError("claude", 500, "internal")
        assert "500" in str(err)
        assert "claude" in str(err)

    def test_backend_response_parse_error_str(self) -> None:
        err = BackendResponseParseError("gpt", "missing key")
        assert "gpt" in str(err)
        assert "missing key" in str(err)


# ===========================================================================
# H: Headers verification
# ===========================================================================

class TestRequestHeaders:
    def test_claude_headers(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-secret-123")
        captured: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response:
            captured.append(request)
            return httpx.Response(200, json=CLAUDE_OK_BODY)

        client = httpx.Client(transport=httpx.MockTransport(handler))
        send_claude({"messages": []}, client=client)
        req = captured[0]
        assert req.headers["x-api-key"] == "sk-secret-123"
        assert req.headers["anthropic-version"] == "2023-06-01"
        assert req.headers["content-type"] == "application/json"

    def test_gpt_headers(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("OPENAI_API_KEY", "sk-secret-456")
        captured: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response:
            captured.append(request)
            return httpx.Response(200, json=GPT_OK_BODY)

        client = httpx.Client(transport=httpx.MockTransport(handler))
        send_gpt({"messages": []}, client=client)
        req = captured[0]
        assert req.headers["authorization"] == "Bearer sk-secret-456"
