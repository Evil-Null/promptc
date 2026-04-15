"""Adapter service — thin orchestration layer delegating to backend adapters."""

from __future__ import annotations

from typing import TYPE_CHECKING, Iterable

from interceptor.adapters.claude import ClaudeAdapter
from interceptor.adapters.gpt import GptAdapter
from interceptor.adapters.models import (
    AdaptedRequest,
    BackendName,
    ExecutionResult,
    StreamEvent,
)
from interceptor.adapters.registry import get_backend_capability

if TYPE_CHECKING:
    import httpx

    from interceptor.compilation.models import CompiledPrompt

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
        compiled_prompt: str | CompiledPrompt,
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
        compiled_prompt: str | CompiledPrompt,
        temperature: float,
        max_output_tokens: int,
        stream: bool = False,
        client: httpx.Client | None = None,
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

    def execute_full(
        self,
        *,
        backend: str,
        compiled_prompt: str | CompiledPrompt,
        temperature: float,
        max_output_tokens: int,
        client: httpx.Client | None = None,
    ) -> ExecutionResult:
        """Execute non-streaming request and return normalized result.

        When *compiled_prompt* is a ``CompiledPrompt`` carrying a non-empty
        ``output_schema_text``, the response is automatically validated against
        the inferred schema format before returning.
        """
        _, adapter = _resolve_adapter(backend)
        request = adapter.adapt(
            compiled_prompt=compiled_prompt,
            temperature=temperature,
            max_output_tokens=max_output_tokens,
            stream=False,
        )
        result = adapter.send_full(request, client=client)

        schema_text: str = getattr(compiled_prompt, "output_schema_text", "")
        if schema_text:
            from interceptor.validation.registry import infer_format, validate_output

            fmt = infer_format(schema_text)
            result.validation = validate_output(result.text, fmt, schema_text)

        hard_gates: list[str] = getattr(compiled_prompt, "quality_gates_hard", [])
        soft_gates: list[str] = getattr(compiled_prompt, "quality_gates_soft", [])
        if hard_gates or soft_gates:
            from interceptor.validation.gate_registry import evaluate_gates

            result.gate_evaluation = evaluate_gates(
                hard_gates=hard_gates,
                soft_gates=soft_gates,
                output=result.text,
            )

        return result

    def execute_stream(
        self,
        *,
        backend: str,
        compiled_prompt: str | CompiledPrompt,
        temperature: float,
        max_output_tokens: int,
        client: httpx.Client | None = None,
    ) -> Iterable[StreamEvent]:
        """Execute streaming request and yield normalized events."""
        _, adapter = _resolve_adapter(backend)
        request = adapter.adapt(
            compiled_prompt=compiled_prompt,
            temperature=temperature,
            max_output_tokens=max_output_tokens,
            stream=True,
        )
        return adapter.stream(request, client=client)
