"""Tests for adapter value objects and enums."""

from __future__ import annotations

import pytest

from interceptor.adapters.models import (
    AdaptedRequest,
    BackendCapability,
    BackendName,
    StreamEvent,
    TemperatureRange,
)


class TestBackendName:
    def test_claude_value(self) -> None:
        assert BackendName.CLAUDE.value == "claude"

    def test_gpt_value(self) -> None:
        assert BackendName.GPT.value == "gpt"

    def test_from_string(self) -> None:
        assert BackendName("claude") is BackendName.CLAUDE

    def test_invalid_raises(self) -> None:
        with pytest.raises(ValueError):
            BackendName("gemini")


class TestTemperatureRange:
    def test_valid(self) -> None:
        tr = TemperatureRange(minimum=0.0, maximum=2.0)
        assert tr.minimum == 0.0
        assert tr.maximum == 2.0

    def test_negative_minimum_raises(self) -> None:
        with pytest.raises(ValueError, match="minimum.*>= 0"):
            TemperatureRange(minimum=-0.1, maximum=1.0)

    def test_max_not_greater_than_min_raises(self) -> None:
        with pytest.raises(ValueError, match="maximum.*exceed.*minimum"):
            TemperatureRange(minimum=1.0, maximum=0.5)

    def test_equal_raises(self) -> None:
        with pytest.raises(ValueError, match="maximum.*exceed.*minimum"):
            TemperatureRange(minimum=1.0, maximum=1.0)


class TestBackendCapability:
    def test_frozen(self) -> None:
        cap = BackendCapability(
            name=BackendName.CLAUDE,
            max_tokens=200_000,
            supports_system_prompt=True,
            supports_structured_output=False,
            supports_streaming=True,
            temperature_range=TemperatureRange(minimum=0.0, maximum=1.0),
            default_temperature=0.7,
        )
        with pytest.raises(AttributeError):
            cap.max_tokens = 999  # type: ignore[misc]

    def test_default_temp_in_range(self) -> None:
        cap = BackendCapability(
            name=BackendName.GPT,
            max_tokens=128_000,
            supports_system_prompt=True,
            supports_structured_output=True,
            supports_streaming=True,
            temperature_range=TemperatureRange(minimum=0.0, maximum=2.0),
            default_temperature=0.7,
        )
        assert (
            cap.temperature_range.minimum
            <= cap.default_temperature
            <= cap.temperature_range.maximum
        )

    def test_negative_max_tokens_raises(self) -> None:
        with pytest.raises(ValueError, match="max_tokens must be positive"):
            BackendCapability(
                name=BackendName.CLAUDE,
                max_tokens=-1,
                supports_system_prompt=True,
                supports_structured_output=False,
                supports_streaming=True,
                temperature_range=TemperatureRange(minimum=0.0, maximum=1.0),
                default_temperature=0.5,
            )

    def test_default_temp_outside_range_raises(self) -> None:
        with pytest.raises(ValueError, match="default_temperature.*outside"):
            BackendCapability(
                name=BackendName.GPT,
                max_tokens=128_000,
                supports_system_prompt=True,
                supports_structured_output=True,
                supports_streaming=True,
                temperature_range=TemperatureRange(minimum=0.0, maximum=1.0),
                default_temperature=1.5,
            )


class TestAdaptedRequest:
    def test_construction(self) -> None:
        req = AdaptedRequest(
            backend=BackendName.CLAUDE,
            payload={"model": "test"},
            temperature=0.5,
            max_output_tokens=4096,
            streaming=False,
        )
        assert req.backend == BackendName.CLAUDE
        assert req.payload == {"model": "test"}
        assert req.streaming is False

    def test_streaming_default(self) -> None:
        req = AdaptedRequest(
            backend=BackendName.GPT,
            payload={},
            temperature=0.7,
            max_output_tokens=1024,
            streaming=False,
        )
        assert req.streaming is False


class TestStreamEvent:
    def test_defaults(self) -> None:
        ev = StreamEvent(type="content")
        assert ev.text == ""
        assert ev.done is False

    def test_done_event(self) -> None:
        ev = StreamEvent(type="done", done=True)
        assert ev.done is True
