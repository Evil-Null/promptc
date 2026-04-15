"""Tests for compiled template cache."""

from __future__ import annotations

import pytest

from interceptor.compilation.cache import CompiledTemplateCache
from interceptor.compilation.models import CompressionLevel
from interceptor.template_registry import TemplateRegistry


@pytest.fixture()
def code_review_template():
    registry = TemplateRegistry.load_all()
    tpl = registry.get("code-review")
    assert tpl is not None
    return tpl


@pytest.fixture()
def explain_template():
    registry = TemplateRegistry.load_all()
    tpl = registry.get("explain")
    assert tpl is not None
    return tpl


class TestCompiledTemplateCache:
    def test_empty_on_init(self) -> None:
        cache = CompiledTemplateCache()
        assert cache.count() == 0

    def test_warm_populates_all_levels(self, code_review_template) -> None:
        cache = CompiledTemplateCache()
        cache.warm_template(code_review_template)
        assert cache.count() == 5  # 5 compression levels

    def test_get_returns_cached(self, code_review_template) -> None:
        cache = CompiledTemplateCache()
        cache.warm_template(code_review_template)
        result = cache.get("code-review", CompressionLevel.NONE)
        assert result is not None
        assert isinstance(result, dict)
        assert "system_directive" in result

    def test_get_miss_returns_none(self) -> None:
        cache = CompiledTemplateCache()
        result = cache.get("nonexistent", CompressionLevel.NONE)
        assert result is None

    def test_idempotent_warm(self, code_review_template) -> None:
        cache = CompiledTemplateCache()
        cache.warm_template(code_review_template)
        count_first = cache.count()
        cache.warm_template(code_review_template)
        count_second = cache.count()
        assert count_first == count_second

    def test_clear_resets(self, code_review_template) -> None:
        cache = CompiledTemplateCache()
        cache.warm_template(code_review_template)
        assert cache.count() > 0
        cache.clear()
        assert cache.count() == 0

    def test_multiple_templates(
        self, code_review_template, explain_template
    ) -> None:
        cache = CompiledTemplateCache()
        cache.warm_template(code_review_template)
        cache.warm_template(explain_template)
        assert cache.count() == 10  # 5 levels × 2 templates

    def test_get_all_levels(self, code_review_template) -> None:
        cache = CompiledTemplateCache()
        cache.warm_template(code_review_template)
        for level in CompressionLevel:
            result = cache.get("code-review", level)
            assert result is not None, f"Missing level {level}"

    def test_cached_content_matches_fresh(self, code_review_template) -> None:
        from interceptor.compilation.compressor import (
            build_template_sections,
            compress_sections,
        )

        cache = CompiledTemplateCache()
        cache.warm_template(code_review_template)

        raw = build_template_sections(code_review_template)
        for level in CompressionLevel:
            fresh, _ = compress_sections(raw, level)
            cached = cache.get("code-review", level)
            assert fresh == cached, f"Mismatch at {level}"
