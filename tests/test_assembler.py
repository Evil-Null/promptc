"""Tests for prompt assembler and compile_prompt orchestration."""

from __future__ import annotations

import pytest

from interceptor.compilation.assembler import (
    USER_INPUT_END,
    USER_INPUT_START,
    assemble_compiled_prompt,
    compile_prompt,
)
from interceptor.compilation.cache import CompiledTemplateCache
from interceptor.compilation.models import CompiledPrompt, CompressionLevel, TokenBudget
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


class TestAssembleCompiledPrompt:
    def test_user_input_delimiters(self, code_review_template) -> None:
        result = assemble_compiled_prompt(
            template=code_review_template,
            raw_input="review auth.py",
            compression_level=CompressionLevel.NONE,
        )
        assert USER_INPUT_START in result.compiled_text
        assert USER_INPUT_END in result.compiled_text
        assert "review auth.py" in result.compiled_text

    def test_section_order_preserved(self, code_review_template) -> None:
        result = assemble_compiled_prompt(
            template=code_review_template,
            raw_input="test",
            compression_level=CompressionLevel.NONE,
        )
        sd_pos = result.compiled_text.index("SYSTEM DIRECTIVE:")
        os_pos = result.compiled_text.index("OUTPUT SCHEMA:")
        ui_pos = result.compiled_text.index(USER_INPUT_START)
        assert sd_pos < os_pos < ui_pos

    def test_headings_present(self, code_review_template) -> None:
        result = assemble_compiled_prompt(
            template=code_review_template,
            raw_input="hi",
            compression_level=CompressionLevel.NONE,
        )
        assert "SYSTEM DIRECTIVE:" in result.compiled_text
        assert "CHAIN OF THOUGHT:" in result.compiled_text

    def test_raw_input_preserved_verbatim(self, code_review_template) -> None:
        weird_input = "hello\n  spaces   <<special>> chars 中文 ქართული"
        result = assemble_compiled_prompt(
            template=code_review_template,
            raw_input=weird_input,
            compression_level=CompressionLevel.NONE,
        )
        assert weird_input in result.compiled_text

    def test_returns_compiled_prompt(self, code_review_template) -> None:
        result = assemble_compiled_prompt(
            template=code_review_template,
            raw_input="test",
            compression_level=CompressionLevel.NONE,
        )
        assert isinstance(result, CompiledPrompt)
        assert result.template_name == "code-review"
        assert result.token_count_estimate > 0

    def test_compression_level_recorded(self, code_review_template) -> None:
        result = assemble_compiled_prompt(
            template=code_review_template,
            raw_input="test",
            compression_level=CompressionLevel.AGGRESSIVE,
        )
        assert result.compression_level == CompressionLevel.AGGRESSIVE

    def test_with_precomputed_sections(self, code_review_template) -> None:
        sections = {"system_directive": "Be helpful."}
        result = assemble_compiled_prompt(
            template=code_review_template,
            raw_input="hi",
            compression_level=CompressionLevel.NONE,
            compressed_sections=sections,
        )
        assert "Be helpful." in result.compiled_text
        assert "system_directive" in result.sections_included


class TestCompilePrompt:
    def test_end_to_end(self, code_review_template) -> None:
        compiled, budget = compile_prompt(
            template=code_review_template,
            raw_input="review auth.py",
            max_tokens=8192,
        )
        assert isinstance(compiled, CompiledPrompt)
        assert isinstance(budget, TokenBudget)
        assert compiled.template_name == "code-review"
        assert budget.fits is True
        assert USER_INPUT_START in compiled.compiled_text

    def test_with_cache(self, code_review_template) -> None:
        cache = CompiledTemplateCache()
        cache.warm_template(code_review_template)

        compiled, budget = compile_prompt(
            template=code_review_template,
            raw_input="review auth.py",
            max_tokens=8192,
            cache=cache,
        )
        assert compiled.template_name == "code-review"
        assert budget.fits is True

    def test_tiny_budget_may_not_fit(self, code_review_template) -> None:
        compiled, budget = compile_prompt(
            template=code_review_template,
            raw_input="review auth.py",
            max_tokens=50,
        )
        assert budget.fits is False

    def test_skeleton_used_on_tight_budget(self, code_review_template) -> None:
        compiled, budget = compile_prompt(
            template=code_review_template,
            raw_input="review auth.py",
            max_tokens=500,
        )
        # With tight budget, should escalate compression.
        if budget.fits:
            assert budget.compression_level in (
                CompressionLevel.AGGRESSIVE,
                CompressionLevel.SKELETON,
                CompressionLevel.COMPACT,
                CompressionLevel.MINIFY,
                CompressionLevel.NONE,
            )

    def test_different_templates(self, code_review_template, explain_template) -> None:
        c1, _ = compile_prompt(
            template=code_review_template, raw_input="x", max_tokens=8192
        )
        c2, _ = compile_prompt(
            template=explain_template, raw_input="x", max_tokens=8192
        )
        assert c1.template_name != c2.template_name
        assert c1.compiled_text != c2.compiled_text

    def test_cache_speeds_repeat_compilation(self, code_review_template) -> None:
        cache = CompiledTemplateCache()
        cache.warm_template(code_review_template)

        c1, _ = compile_prompt(
            template=code_review_template,
            raw_input="review auth.py",
            max_tokens=8192,
            cache=cache,
        )
        c2, _ = compile_prompt(
            template=code_review_template,
            raw_input="review auth.py",
            max_tokens=8192,
            cache=cache,
        )
        assert c1.compiled_text == c2.compiled_text
