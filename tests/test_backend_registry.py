"""Tests for the static backend capability registry."""

from __future__ import annotations

import pytest

from interceptor.adapters.models import BackendCapability, BackendName
from interceptor.adapters.registry import (
    get_backend_capability,
    has_backend,
    list_backend_capabilities,
)


class TestGetBackendCapability:
    def test_claude_by_enum(self) -> None:
        cap = get_backend_capability(BackendName.CLAUDE)
        assert cap.name == BackendName.CLAUDE
        assert cap.max_tokens == 200_000

    def test_gpt_by_string(self) -> None:
        cap = get_backend_capability("gpt")
        assert cap.name == BackendName.GPT
        assert cap.max_tokens == 128_000

    def test_unknown_raises(self) -> None:
        with pytest.raises(ValueError, match="Unknown backend"):
            get_backend_capability("gemini")


class TestListBackendCapabilities:
    def test_returns_all(self) -> None:
        caps = list_backend_capabilities()
        assert len(caps) == 2
        names = {c.name for c in caps}
        assert names == {BackendName.CLAUDE, BackendName.GPT}

    def test_all_are_capabilities(self) -> None:
        for cap in list_backend_capabilities():
            assert isinstance(cap, BackendCapability)

    def test_deterministic_order(self) -> None:
        a = list_backend_capabilities()
        b = list_backend_capabilities()
        assert [c.name for c in a] == [c.name for c in b]


class TestHasBackend:
    def test_claude_exists(self) -> None:
        assert has_backend("claude") is True

    def test_gpt_exists(self) -> None:
        assert has_backend("gpt") is True

    def test_unknown_returns_false(self) -> None:
        assert has_backend("llama") is False

    def test_empty_string_returns_false(self) -> None:
        assert has_backend("") is False


class TestRegistryValues:
    """Verify plan-aligned capability values (section 4.15)."""

    def test_claude_caps(self) -> None:
        cap = get_backend_capability("claude")
        assert cap.supports_system_prompt is True
        assert cap.supports_structured_output is False
        assert cap.supports_streaming is True
        assert cap.temperature_range.minimum == 0.0
        assert cap.temperature_range.maximum == 1.0
        assert cap.default_temperature == 0.7

    def test_gpt_caps(self) -> None:
        cap = get_backend_capability("gpt")
        assert cap.supports_system_prompt is True
        assert cap.supports_structured_output is True
        assert cap.supports_streaming is True
        assert cap.temperature_range.minimum == 0.0
        assert cap.temperature_range.maximum == 2.0
        assert cap.default_temperature == 0.7
