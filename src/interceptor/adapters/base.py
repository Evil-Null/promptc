"""Abstract adapter protocol — the contract every backend adapter implements."""

from __future__ import annotations

from typing import TYPE_CHECKING, Iterable, Protocol

if TYPE_CHECKING:
    from interceptor.adapters.models import (
        AdaptedRequest,
        BackendName,
        StreamEvent,
    )


class BackendAdapter(Protocol):
    """Protocol that every backend adapter must satisfy."""

    backend_name: BackendName

    def adapt(
        self,
        *,
        compiled_prompt: str,
        temperature: float,
        max_output_tokens: int,
        stream: bool,
    ) -> AdaptedRequest:
        """Build a backend-specific request payload (pure, no side effects)."""
        ...

    def send(
        self, request: AdaptedRequest, *, client: object | None = None
    ) -> str:
        """Execute a synchronous request and return the response text."""
        ...

    def stream(
        self, request: AdaptedRequest, *, client: object | None = None
    ) -> Iterable[StreamEvent]:
        """Execute a streaming request and yield events."""
        ...
