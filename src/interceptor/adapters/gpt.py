"""GPT backend adapter — maps compiled prompts to OpenAI Chat Completions shape."""

from __future__ import annotations

from typing import TYPE_CHECKING, Iterable

from interceptor.adapters.models import (
    AdaptedRequest,
    BackendName,
    StreamEvent,
)
from interceptor.adapters.prompt_extract import extract_system_text, extract_user_text

if TYPE_CHECKING:
    from interceptor.compilation.models import CompiledPrompt

DEFAULT_MODEL = "gpt-4o"


class GptAdapter:
    """Adapter for the OpenAI Chat Completions API."""

    backend_name: BackendName = BackendName.GPT

    def adapt(
        self,
        *,
        compiled_prompt: str | CompiledPrompt,
        temperature: float,
        max_output_tokens: int,
        stream: bool,
    ) -> AdaptedRequest:
        if isinstance(compiled_prompt, str):
            system_text = compiled_prompt
            user_text = compiled_prompt
        else:
            system_text = extract_system_text(compiled_prompt)
            user_text = extract_user_text(compiled_prompt)

        payload: dict = {
            "model": DEFAULT_MODEL,
            "messages": [
                {"role": "system", "content": system_text},
                {"role": "user", "content": user_text},
            ],
            "max_tokens": max_output_tokens,
            "temperature": temperature,
            "stream": stream,
        }
        return AdaptedRequest(
            backend=BackendName.GPT,
            payload=payload,
            temperature=temperature,
            max_output_tokens=max_output_tokens,
            streaming=stream,
        )

    def send(
        self, request: AdaptedRequest, *, client: object | None = None
    ) -> str:
        if client is None:
            raise RuntimeError(
                "GptAdapter.send() requires a client (no live calls in V1)"
            )
        send_fn = getattr(client, "send", None)
        if send_fn is None or not callable(send_fn):
            raise TypeError("client must implement send(request) -> str")
        result: str = send_fn(request)
        return result

    def stream(
        self, request: AdaptedRequest, *, client: object | None = None
    ) -> Iterable[StreamEvent]:
        if client is None:
            raise RuntimeError(
                "GptAdapter.stream() requires a client (no live calls in V1)"
            )
        stream_fn = getattr(client, "stream", None)
        if stream_fn is None or not callable(stream_fn):
            raise TypeError("client must implement stream(request) -> Iterable[StreamEvent]")
        yield from stream_fn(request)
