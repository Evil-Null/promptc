"""Adapter service — thin orchestration layer delegating to backend adapters."""

from __future__ import annotations

from typing import Iterable

from interceptor.adapters.claude import ClaudeAdapter
from interceptor.adapters.gpt import GptAdapter
from interceptor.adapters.models import (
    AdaptedRequest,
    BackendName,
    StreamEvent,
)
from interceptor.adapters.registry import get_backend_capability

_ADAPTERS = {
    BackendName.CLAUDE: ClaudeAdapter(),
    BackendName.GPT: GptAdapter(),
}


def _resolve_adapter(backend: str) -> tuple[BackendName, ClaudeAdapter | GptAdapter]:
    cap = get_backend_capability(backend)
    adapter = _ADAPTERS.get(cap.name)
    if adapter is None:
        raise ValueError(f"No adapter registered for backend {backend!r}")
    return cap.name, adapter


class AdapterService:
    """Delegates adapt/execute to the correct backend adapter."""

    def adapt_request(
        self,
        *,
        backend: str,
        compiled_prompt: str,
        temperature: float,
        max_output_tokens: int,
        stream: bool = False,
    ) -> AdaptedRequest:
        _, adapter = _resolve_adapter(backend)
        return adapter.adapt(
            compiled_prompt=compiled_prompt,
            temperature=temperature,
            max_output_tokens=max_output_tokens,
            stream=stream,
        )

    def execute(
        self,
        *,
        backend: str,
        compiled_prompt: str,
        temperature: float,
        max_output_tokens: int,
        stream: bool = False,
        client: object | None = None,
    ) -> str | Iterable[StreamEvent]:
        """Return response text (stream=False) or StreamEvent iterable (stream=True)."""
        _, adapter = _resolve_adapter(backend)
        request = adapter.adapt(
            compiled_prompt=compiled_prompt,
            temperature=temperature,
            max_output_tokens=max_output_tokens,
            stream=stream,
        )
        if stream:
            return adapter.stream(request, client=client)
        return adapter.send(request, client=client)
