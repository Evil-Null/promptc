"""Static backend capability registry — plan-aligned values."""

from __future__ import annotations

from interceptor.adapters.models import (
    BackendCapability,
    BackendName,
    TemperatureRange,
)

_REGISTRY: dict[BackendName, BackendCapability] = {
    BackendName.CLAUDE: BackendCapability(
        name=BackendName.CLAUDE,
        max_tokens=200_000,
        supports_system_prompt=True,
        supports_structured_output=False,
        supports_streaming=True,
        temperature_range=TemperatureRange(minimum=0.0, maximum=1.0),
        default_temperature=0.7,
    ),
    BackendName.GPT: BackendCapability(
        name=BackendName.GPT,
        max_tokens=128_000,
        supports_system_prompt=True,
        supports_structured_output=True,
        supports_streaming=True,
        temperature_range=TemperatureRange(minimum=0.0, maximum=2.0),
        default_temperature=0.7,
    ),
}


def get_backend_capability(name: str | BackendName) -> BackendCapability:
    """Return capability descriptor for *name*.

    Raises ``ValueError`` if the backend is not registered.
    """
    try:
        key = BackendName(name) if not isinstance(name, BackendName) else name
    except ValueError:
        registered = ", ".join(sorted(b.value for b in _REGISTRY))
        raise ValueError(
            f"Unknown backend {name!r}. Registered: {registered}"
        ) from None
    cap = _REGISTRY.get(key)
    if cap is None:
        registered = ", ".join(sorted(b.value for b in _REGISTRY))
        raise ValueError(
            f"Unknown backend {name!r}. Registered: {registered}"
        )
    return cap


def list_backend_capabilities() -> list[BackendCapability]:
    """Return all registered capabilities in deterministic order."""
    return [_REGISTRY[k] for k in sorted(_REGISTRY)]


def has_backend(name: str) -> bool:
    """Return ``True`` if *name* is a registered backend."""
    try:
        BackendName(name)
    except ValueError:
        return False
    return BackendName(name) in _REGISTRY
