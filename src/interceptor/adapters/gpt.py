"""GPT backend adapter — maps compiled prompts to OpenAI Chat Completions shape."""

from __future__ import annotations

from typing import TYPE_CHECKING, Iterable

from interceptor.adapters.models import (
    AdaptedRequest,
    BackendName,
    ExecutionResult,
    StreamEvent,
)
from interceptor.adapters.prompt_extract import extract_system_text, extract_user_text

if TYPE_CHECKING:
    import httpx

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
        self, request: AdaptedRequest, *, client: httpx.Client | None = None
    ) -> str:
        from interceptor.adapters.transport import send_gpt

        result = send_gpt(request.payload, client=client)
        return result.text

    def send_full(
        self, request: AdaptedRequest, *, client: httpx.Client | None = None
    ) -> ExecutionResult:
        from interceptor.adapters.transport import send_gpt

        return send_gpt(request.payload, client=client)

    def stream(
        self, request: AdaptedRequest, *, client: httpx.Client | None = None
    ) -> Iterable[StreamEvent]:
        from interceptor.adapters.transport import stream_gpt

        return stream_gpt(request.payload, client=client)
