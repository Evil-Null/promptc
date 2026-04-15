"""Capability-based backend selector."""

from __future__ import annotations

from interceptor.adapters.models import BackendCapability
from interceptor.adapters.registry import (
    get_backend_capability,
    list_backend_capabilities,
)


def _satisfies(
    cap: BackendCapability,
    *,
    require_structured_output: bool,
    require_streaming: bool,
) -> bool:
    if require_structured_output and not cap.supports_structured_output:
        return False
    if require_streaming and not cap.supports_streaming:
        return False
    return True


def select_backend(
    *,
    preferred: str | None = None,
    require_structured_output: bool = False,
    require_streaming: bool = False,
) -> BackendCapability:
    """Select a backend by preference, falling back on capability match.

    If *preferred* satisfies all requirements, return it.  Otherwise pick the
    first registered backend that does.  Raises ``ValueError`` when no backend
    matches.
    """
    if preferred is not None:
        try:
            cap = get_backend_capability(preferred)
        except ValueError:
            pass
        else:
            if _satisfies(
                cap,
                require_structured_output=require_structured_output,
                require_streaming=require_streaming,
            ):
                return cap

    for cap in list_backend_capabilities():
        if _satisfies(
            cap,
            require_structured_output=require_structured_output,
            require_streaming=require_streaming,
        ):
            return cap

    parts: list[str] = []
    if require_structured_output:
        parts.append("structured_output")
    if require_streaming:
        parts.append("streaming")
    raise ValueError(
        f"No backend satisfies requirements: {', '.join(parts)}"
    )
