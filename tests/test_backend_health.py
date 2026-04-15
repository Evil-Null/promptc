"""Tests for the backends_valid health check."""

from __future__ import annotations

from interceptor.health import check_backends_valid


class TestBackendsValid:
    def test_passes_with_default_registry(self) -> None:
        result = check_backends_valid()
        assert result.name == "backends_valid"
        assert result.status == "pass"

    def test_message_includes_count(self) -> None:
        result = check_backends_valid()
        assert "2" in result.message

    def test_all_have_adapters(self) -> None:
        result = check_backends_valid()
        assert result.status == "pass"
        assert "valid with adapters" in result.message

    def test_empty_registry_fails(self, monkeypatch: object) -> None:
        """Simulate empty registry → fail."""
        import interceptor.health as health_mod

        monkeypatch.setattr(  # type: ignore[attr-defined]
            health_mod,
            "check_backends_valid",
            check_backends_valid,
        )
        from interceptor.adapters import registry as reg_mod

        original = reg_mod._REGISTRY.copy()
        reg_mod._REGISTRY.clear()
        try:
            result = check_backends_valid()
            assert result.status == "fail"
            assert "No backends" in result.message
        finally:
            reg_mod._REGISTRY.update(original)

    def test_missing_adapter_fails(self, monkeypatch: object) -> None:
        """Simulate adapter missing for a registered backend → fail."""
        from interceptor.adapters import service as svc_mod
        from interceptor.adapters.models import BackendName

        original = svc_mod._ADAPTERS.copy()
        del svc_mod._ADAPTERS[BackendName.CLAUDE]
        try:
            result = check_backends_valid()
            assert result.status == "fail"
            assert "no adapter" in result.message
        finally:
            svc_mod._ADAPTERS.update(original)
