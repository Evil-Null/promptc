"""Backend adapters — capability registry, adaptation, and transport."""

from interceptor.adapters.models import (
    AdaptedRequest,
    BackendCapability,
    BackendName,
    StreamEvent,
    TemperatureRange,
)
from interceptor.adapters.registry import (
    get_backend_capability,
    has_backend,
    list_backend_capabilities,
)
from interceptor.adapters.selector import select_backend
from interceptor.adapters.claude import ClaudeAdapter
from interceptor.adapters.gpt import GptAdapter
from interceptor.adapters.service import AdapterService

__all__ = [
    "AdaptedRequest",
    "AdapterService",
    "BackendCapability",
    "BackendName",
    "ClaudeAdapter",
    "GptAdapter",
    "StreamEvent",
    "TemperatureRange",
    "get_backend_capability",
    "has_backend",
    "list_backend_capabilities",
    "select_backend",
]
