"""Minimal HTTP transport for backend adapters."""

from __future__ import annotations

import json as json_mod
import os
from collections.abc import Iterator

import httpx

from interceptor.adapters.errors import (
    BackendRequestError,
    BackendResponseParseError,
    MissingApiKeyError,
)
from interceptor.adapters.models import ExecutionResult, StreamEvent

CLAUDE_API_URL = "https://api.anthropic.com/v1/messages"
CLAUDE_API_VERSION = "2023-06-01"
OPENAI_API_URL = "https://api.openai.com/v1/chat/completions"

REQUEST_TIMEOUT = 120.0

_OAUTH_TOKEN_PREFIX = "sk-ant-oat01-"
_CLAUDE_OAUTH_BETAS = "prompt-caching-2024-07-31,oauth-2025-04-20"
_CC_BILLING_HEADER = (
    "x-anthropic-billing-header: cc_version=2.1.63.0a5;"
    " cc_entrypoint=cli; cch=00000;"
)


def _get_api_key(env_var: str, backend: str) -> str:
    key = os.environ.get(env_var, "")
    if not key:
        raise MissingApiKeyError(env_var, backend)
    return key


def _is_oauth_token(api_key: str) -> bool:
    """Return True if the key is a Claude OAuth/setup token."""
    return api_key.startswith(_OAUTH_TOKEN_PREFIX)


def _build_claude_headers(api_key: str) -> dict[str, str]:
    """Build appropriate headers based on API key type."""
    if _is_oauth_token(api_key):
        return {
            "Authorization": f"Bearer {api_key}",
            "anthropic-version": CLAUDE_API_VERSION,
            "anthropic-beta": _CLAUDE_OAUTH_BETAS,
            "content-type": "application/json",
        }
    return {
        "x-api-key": api_key,
        "anthropic-version": CLAUDE_API_VERSION,
        "content-type": "application/json",
    }


def _inject_billing_attribution(payload: dict, api_key: str) -> dict:
    """Prepend billing attribution to system prompt for OAuth tokens."""
    if not _is_oauth_token(api_key):
        return payload
    payload = {**payload}  # shallow copy
    system = payload.get("system", "")
    if isinstance(system, str):
        payload["system"] = (
            f"{_CC_BILLING_HEADER}\n{system}" if system else _CC_BILLING_HEADER
        )
    elif isinstance(system, list):
        payload["system"] = [
            {"type": "text", "text": _CC_BILLING_HEADER},
        ] + system
    return payload


# ---------------------------------------------------------------------------
# Non-streaming send
# ---------------------------------------------------------------------------


def send_claude(
    payload: dict,
    *,
    client: httpx.Client | None = None,
) -> ExecutionResult:
    """Send a non-streaming request to Claude Messages API."""
    api_key = _get_api_key("ANTHROPIC_API_KEY", "claude")
    headers = _build_claude_headers(api_key)
    send_payload = _inject_billing_attribution({**payload, "stream": False}, api_key)

    owns_client = client is None
    if owns_client:
        client = httpx.Client(timeout=REQUEST_TIMEOUT)
    try:
        resp = client.post(CLAUDE_API_URL, headers=headers, json=send_payload)
    finally:
        if owns_client:
            client.close()

    if resp.status_code != 200:
        raise BackendRequestError("claude", resp.status_code, resp.text[:500])

    try:
        body = resp.json()
        content_blocks = body["content"]
        text_parts = [
            block["text"] for block in content_blocks if block.get("type") == "text"
        ]
        text = "".join(text_parts)
    except (KeyError, TypeError, ValueError) as exc:
        raise BackendResponseParseError("claude", str(exc)) from exc

    return ExecutionResult(
        backend="claude",
        text=text,
        finish_reason=body.get("stop_reason"),
        usage_input_tokens=body.get("usage", {}).get("input_tokens"),
        usage_output_tokens=body.get("usage", {}).get("output_tokens"),
    )


def send_gpt(
    payload: dict,
    *,
    client: httpx.Client | None = None,
) -> ExecutionResult:
    """Send a non-streaming request to OpenAI Chat Completions API."""
    api_key = _get_api_key("OPENAI_API_KEY", "gpt")
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    send_payload = {**payload, "stream": False}

    owns_client = client is None
    if owns_client:
        client = httpx.Client(timeout=REQUEST_TIMEOUT)
    try:
        resp = client.post(OPENAI_API_URL, headers=headers, json=send_payload)
    finally:
        if owns_client:
            client.close()

    if resp.status_code != 200:
        raise BackendRequestError("gpt", resp.status_code, resp.text[:500])

    try:
        body = resp.json()
        choice = body["choices"][0]
        text = choice["message"]["content"]
    except (KeyError, TypeError, IndexError, ValueError) as exc:
        raise BackendResponseParseError("gpt", str(exc)) from exc

    return ExecutionResult(
        backend="gpt",
        text=text,
        finish_reason=choice.get("finish_reason"),
        usage_input_tokens=body.get("usage", {}).get("prompt_tokens"),
        usage_output_tokens=body.get("usage", {}).get("completion_tokens"),
    )


# ---------------------------------------------------------------------------
# Streaming send
# ---------------------------------------------------------------------------


def stream_claude(
    payload: dict,
    *,
    client: httpx.Client | None = None,
) -> Iterator[StreamEvent]:
    """Stream a request to Claude Messages API, yielding normalized events."""
    api_key = _get_api_key("ANTHROPIC_API_KEY", "claude")
    headers = _build_claude_headers(api_key)
    send_payload = _inject_billing_attribution({**payload, "stream": True}, api_key)

    owns_client = client is None
    if owns_client:
        client = httpx.Client(timeout=REQUEST_TIMEOUT)
    try:
        with client.stream(
            "POST", CLAUDE_API_URL, headers=headers, json=send_payload
        ) as resp:
            if resp.status_code != 200:
                resp.read()
                raise BackendRequestError(
                    "claude", resp.status_code, resp.text[:500]
                )
            for line in resp.iter_lines():
                if not line or line.startswith("event:"):
                    continue
                if not line.startswith("data: "):
                    continue
                raw = line[6:]
                try:
                    data = json_mod.loads(raw)
                except (json_mod.JSONDecodeError, ValueError) as exc:
                    raise BackendResponseParseError(
                        "claude", f"malformed SSE data: {raw[:200]}"
                    ) from exc
                event_type = data.get("type", "")
                if event_type == "content_block_delta":
                    delta = data.get("delta", {})
                    if delta.get("type") == "text_delta":
                        yield StreamEvent(
                            type="content", text=delta.get("text", "")
                        )
                elif event_type == "message_delta":
                    yield StreamEvent(type="done", done=True)
    finally:
        if owns_client:
            client.close()


def stream_gpt(
    payload: dict,
    *,
    client: httpx.Client | None = None,
) -> Iterator[StreamEvent]:
    """Stream a request to OpenAI Chat Completions API, yielding normalized events."""
    api_key = _get_api_key("OPENAI_API_KEY", "gpt")
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    send_payload = {**payload, "stream": True}

    owns_client = client is None
    if owns_client:
        client = httpx.Client(timeout=REQUEST_TIMEOUT)
    try:
        with client.stream(
            "POST", OPENAI_API_URL, headers=headers, json=send_payload
        ) as resp:
            if resp.status_code != 200:
                resp.read()
                raise BackendRequestError(
                    "gpt", resp.status_code, resp.text[:500]
                )
            for line in resp.iter_lines():
                if not line or not line.startswith("data: "):
                    continue
                raw = line[6:]
                if raw == "[DONE]":
                    yield StreamEvent(type="done", done=True)
                    return
                try:
                    data = json_mod.loads(raw)
                except (json_mod.JSONDecodeError, ValueError) as exc:
                    raise BackendResponseParseError(
                        "gpt", f"malformed SSE data: {raw[:200]}"
                    ) from exc
                choices = data.get("choices", [])
                if choices:
                    delta = choices[0].get("delta", {})
                    content = delta.get("content")
                    if content:
                        yield StreamEvent(type="content", text=content)
    finally:
        if owns_client:
            client.close()
