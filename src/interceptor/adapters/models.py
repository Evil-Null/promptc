"""Backend capability models — frozen value types for adapter layer."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class BackendName(StrEnum):
    """Known backend identifiers."""

    CLAUDE = "claude"
    GPT = "gpt"


@dataclass(slots=True, frozen=True)
class TemperatureRange:
    """Valid temperature bounds for a backend."""

    minimum: float
    maximum: float

    def __post_init__(self) -> None:
        if self.minimum < 0:
            raise ValueError(f"minimum must be >= 0, got {self.minimum}")
        if self.maximum <= self.minimum:
            raise ValueError(
                f"maximum ({self.maximum}) must exceed minimum ({self.minimum})"
            )


@dataclass(slots=True, frozen=True)
class BackendCapability:
    """Static capability descriptor for one backend."""

    name: BackendName
    max_tokens: int
    supports_system_prompt: bool
    supports_structured_output: bool
    supports_streaming: bool
    temperature_range: TemperatureRange
    default_temperature: float

    def __post_init__(self) -> None:
        if self.max_tokens <= 0:
            raise ValueError(f"max_tokens must be positive, got {self.max_tokens}")
        if not (
            self.temperature_range.minimum
            <= self.default_temperature
            <= self.temperature_range.maximum
        ):
            raise ValueError(
                f"default_temperature {self.default_temperature} outside "
                f"range [{self.temperature_range.minimum}, {self.temperature_range.maximum}]"
            )


@dataclass(slots=True)
class AdaptedRequest:
    """Backend-specific request payload ready for transport."""

    backend: BackendName
    payload: dict
    temperature: float
    max_output_tokens: int
    streaming: bool


@dataclass(slots=True)
class StreamEvent:
    """Single streaming event from a backend response."""

    type: str
    text: str = ""
    done: bool = False


@dataclass(slots=True)
class ExecutionResult:
    """Normalized result from a backend send execution."""

    backend: str
    text: str
    finish_reason: str | None = None
    usage_input_tokens: int | None = None
    usage_output_tokens: int | None = None
