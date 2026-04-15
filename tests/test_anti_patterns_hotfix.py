"""PR-6 regression tests — anti_patterns TOML placement hotfix.

Pins the fix: anti_patterns must load at the Template root, not inside
quality_gates.  Also verifies compiled output includes the ANTI-PATTERNS
section when compression retains it.
"""

from __future__ import annotations

import pytest

from interceptor.compilation.assembler import assemble_compiled_prompt
from interceptor.compilation.compressor import build_template_sections, compress_sections
from interceptor.compilation.models import CompressionLevel
from interceptor.template_registry import TemplateRegistry

_BUILTIN_NAMES = ("code-review", "architecture", "explain", "security-audit")


@pytest.fixture(scope="module")
def registry() -> TemplateRegistry:
    return TemplateRegistry.load_all()


# ------------------------------------------------------------------
# 1. anti_patterns loads at Template root (non-empty)
# ------------------------------------------------------------------
class TestAntiPatternsRootField:
    @pytest.mark.parametrize("name", _BUILTIN_NAMES)
    def test_anti_patterns_is_non_empty_list(
        self, registry: TemplateRegistry, name: str
    ) -> None:
        tpl = registry.get(name)
        assert isinstance(tpl.anti_patterns, list)
        assert len(tpl.anti_patterns) >= 1, (
            f"{name}: anti_patterns must not be empty"
        )

    @pytest.mark.parametrize("name", _BUILTIN_NAMES)
    def test_anti_patterns_items_are_non_empty_strings(
        self, registry: TemplateRegistry, name: str
    ) -> None:
        tpl = registry.get(name)
        for item in tpl.anti_patterns:
            assert isinstance(item, str)
            assert item.strip(), f"{name}: anti_patterns item must not be blank"


# ------------------------------------------------------------------
# 2. quality_gates no longer contains anti_patterns data
# ------------------------------------------------------------------
class TestQualityGatesClean:
    @pytest.mark.parametrize("name", _BUILTIN_NAMES)
    def test_quality_gates_has_no_anti_patterns_attr(
        self, registry: TemplateRegistry, name: str
    ) -> None:
        tpl = registry.get(name)
        assert not hasattr(tpl.quality_gates, "anti_patterns"), (
            f"{name}: quality_gates should not carry anti_patterns"
        )


# ------------------------------------------------------------------
# 3. Registry-loaded builtins preserve anti_patterns
# ------------------------------------------------------------------
class TestRegistryPreservation:
    def test_all_builtins_have_anti_patterns(
        self, registry: TemplateRegistry
    ) -> None:
        for name in _BUILTIN_NAMES:
            tpl = registry.get(name)
            assert tpl.anti_patterns, f"{name}: anti_patterns missing after registry load"

    def test_code_review_specific_anti_patterns(
        self, registry: TemplateRegistry
    ) -> None:
        tpl = registry.get("code-review")
        assert "Rubber-stamp approval without analysis" in tpl.anti_patterns
        assert "Nitpicking style over substance" in tpl.anti_patterns
        assert "Missing security review" in tpl.anti_patterns


# ------------------------------------------------------------------
# 4. Compiled prompt includes ANTI-PATTERNS section
# ------------------------------------------------------------------
class TestCompiledOutputIncludesAntiPatterns:
    def test_none_level_includes_anti_patterns_section(
        self, registry: TemplateRegistry
    ) -> None:
        tpl = registry.get("code-review")
        compiled = assemble_compiled_prompt(
            template=tpl,
            raw_input="review auth.py",
            compression_level=CompressionLevel.NONE,
        )
        assert "ANTI-PATTERNS:" in compiled.compiled_text
        assert "anti_patterns" in compiled.sections_included

    def test_compact_level_includes_anti_patterns_section(
        self, registry: TemplateRegistry
    ) -> None:
        tpl = registry.get("security-audit")
        compiled = assemble_compiled_prompt(
            template=tpl,
            raw_input="audit login.py",
            compression_level=CompressionLevel.COMPACT,
        )
        assert "ANTI-PATTERNS:" in compiled.compiled_text
        assert "anti_patterns" in compiled.sections_included

    def test_skeleton_level_omits_anti_patterns(
        self, registry: TemplateRegistry
    ) -> None:
        tpl = registry.get("code-review")
        compiled = assemble_compiled_prompt(
            template=tpl,
            raw_input="review auth.py",
            compression_level=CompressionLevel.SKELETON,
        )
        assert "ANTI-PATTERNS:" not in compiled.compiled_text
        assert "anti_patterns" not in compiled.sections_included

    def test_anti_patterns_content_present_in_output(
        self, registry: TemplateRegistry
    ) -> None:
        tpl = registry.get("code-review")
        compiled = assemble_compiled_prompt(
            template=tpl,
            raw_input="review auth.py",
            compression_level=CompressionLevel.NONE,
        )
        assert "Rubber-stamp approval" in compiled.compiled_text


# ------------------------------------------------------------------
# 5. Compressor build_template_sections emits anti_patterns
# ------------------------------------------------------------------
class TestCompressorSectionsAntiPatterns:
    def test_build_sections_includes_anti_patterns_key(
        self, registry: TemplateRegistry
    ) -> None:
        tpl = registry.get("code-review")
        sections = build_template_sections(tpl)
        assert "anti_patterns" in sections
        assert "Rubber-stamp" in sections["anti_patterns"]

    @pytest.mark.parametrize("name", _BUILTIN_NAMES)
    def test_all_builtins_emit_anti_patterns_section(
        self, registry: TemplateRegistry, name: str
    ) -> None:
        tpl = registry.get(name)
        sections = build_template_sections(tpl)
        assert "anti_patterns" in sections, (
            f"{name}: build_template_sections should emit anti_patterns"
        )

    def test_compress_none_preserves_anti_patterns(
        self, registry: TemplateRegistry
    ) -> None:
        tpl = registry.get("code-review")
        raw = build_template_sections(tpl)
        compressed, included = compress_sections(raw, CompressionLevel.NONE)
        assert "anti_patterns" in compressed
        assert "anti_patterns" in included
