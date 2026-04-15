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


def _evaluate_result(
    result: ExecutionResult,
    compiled_prompt: str | CompiledPrompt,
) -> None:
    """Run schema validation and gate evaluation on *result* in-place."""
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
        """Execute non-streaming request with retry on validation/gate failure.

        When *compiled_prompt* is a ``CompiledPrompt`` carrying a non-empty
        ``output_schema_text`` or quality gates, the response is validated and
        retried with escalating strictness if it fails.
        """
        _, adapter = _resolve_adapter(backend)
        request = adapter.adapt(
            compiled_prompt=compiled_prompt,
            temperature=temperature,
            max_output_tokens=max_output_tokens,
            stream=False,
        )
        result = adapter.send_full(request, client=client)
        _evaluate_result(result, compiled_prompt)

        if not hasattr(compiled_prompt, "compiled_text"):
            return result

        from interceptor.validation.retry_engine import (
            build_retry_prompt,
            classify_failure,
            should_stop_same_failure,
        )
        from interceptor.validation.retry_models import (
            FailureCategory,
            RetryOutcome,
            RetryResult,
            STRICTNESS_ORDER,
        )

        failure = classify_failure(result.validation, result.gate_evaluation)
        if failure is None:
            result.retry_result = RetryResult(
                attempts=1,
                outcome=RetryOutcome.NOT_NEEDED,
            )
            return result

        failure_reasons: list[FailureCategory] = [failure]
        attempts = 1

        for strictness in STRICTNESS_ORDER:
            attempts += 1
            retry_prompt = build_retry_prompt(compiled_prompt, strictness)
            retry_request = adapter.adapt(
                compiled_prompt=retry_prompt,
                temperature=temperature,
                max_output_tokens=max_output_tokens,
                stream=False,
            )
            result = adapter.send_full(retry_request, client=client)
            _evaluate_result(result, compiled_prompt)

            failure = classify_failure(result.validation, result.gate_evaluation)
            if failure is None:
                result.retry_result = RetryResult(
                    attempts=attempts,
                    outcome=RetryOutcome.RECOVERED,
                    final_strictness=strictness,
                    failure_reasons=failure_reasons,
                )
                return result

            failure_reasons.append(failure)

            if should_stop_same_failure(failure_reasons):
                result.retry_result = RetryResult(
                    attempts=attempts,
                    outcome=RetryOutcome.EXHAUSTED,
                    final_strictness=strictness,
                    failure_reasons=failure_reasons,
                    same_failure_stopped=True,
                )
                return result

        result.retry_result = RetryResult(
            attempts=attempts,
            outcome=RetryOutcome.EXHAUSTED,
            final_strictness=STRICTNESS_ORDER[-1],
            failure_reasons=failure_reasons,
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
