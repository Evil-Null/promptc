"""Minimal HTTP transport for backend adapters."""

from __future__ import annotations

import os

import httpx

from interceptor.adapters.errors import (
    BackendRequestError,
    BackendResponseParseError,
    MissingApiKeyError,
)
from interceptor.adapters.models import ExecutionResult

CLAUDE_API_URL = "https://api.anthropic.com/v1/messages"
CLAUDE_API_VERSION = "2023-06-01"
OPENAI_API_URL = "https://api.openai.com/v1/chat/completions"

REQUEST_TIMEOUT = 120.0


def _get_api_key(env_var: str, backend: str) -> str:
    key = os.environ.get(env_var, "")
    if not key:
        raise MissingApiKeyError(env_var, backend)
    return key


def send_claude(
    payload: dict,
    *,
    client: httpx.Client | None = None,
) -> ExecutionResult:
    """Send a non-streaming request to Claude Messages API."""
    api_key = _get_api_key("ANTHROPIC_API_KEY", "claude")
    headers = {
        "x-api-key": api_key,
        "anthropic-version": CLAUDE_API_VERSION,
        "content-type": "application/json",
    }
    send_payload = {**payload, "stream": False}

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
