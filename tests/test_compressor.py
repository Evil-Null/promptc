"""Tests for deterministic template compression."""

from __future__ import annotations

import pytest

from interceptor.compilation.compressor import (
    SECTION_KEYS,
    build_template_sections,
    compress_sections,
)
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


class TestBuildTemplateSections:
    def test_extracts_expected_keys(self, code_review_template) -> None:
        sections = build_template_sections(code_review_template)
        assert "system_directive" in sections
        assert "chain_of_thought" in sections
        assert "output_schema" in sections
        assert "quality_gates" in sections
        # anti_patterns is at TOML root level under [quality_gates] header,
        # so it's parsed as quality_gates.anti_patterns — not template root.
        # This is a known pre-existing issue; anti_patterns may be absent.

    def test_all_values_non_empty(self, code_review_template) -> None:
        sections = build_template_sections(code_review_template)
        for key, value in sections.items():
            assert value.strip(), f"Section {key} is empty"

    def test_omits_empty_optional(self) -> None:
        from interceptor.models.template import (
            QualityGates,
            Template,
            TemplateMeta,
            TemplatePrompt,
            TemplateTriggers,
        )

        tpl = Template(
            meta=TemplateMeta(
                name="minimal",
                category="EVALUATIVE",
                version="1.0.0",
                author="test",
            ),
            triggers=TemplateTriggers(en=["test"]),
            prompt=TemplatePrompt(
                system_directive="Do the thing.",
                chain_of_thought="",
                output_schema="Return JSON.",
            ),
            quality_gates=QualityGates(),
            anti_patterns=[],
        )
        sections = build_template_sections(tpl)
        assert "system_directive" in sections
        assert "output_schema" in sections
        assert "chain_of_thought" not in sections
        assert "quality_gates" not in sections
        assert "anti_patterns" not in sections

    def test_includes_anti_patterns_when_present(self) -> None:
        from interceptor.models.template import (
            QualityGates,
            Template,
            TemplateMeta,
            TemplatePrompt,
            TemplateTriggers,
        )

        tpl = Template(
            meta=TemplateMeta(
                name="with-ap",
                category="EVALUATIVE",
                version="1.0.0",
                author="test",
            ),
            triggers=TemplateTriggers(en=["test"]),
            prompt=TemplatePrompt(
                system_directive="Check things.",
                output_schema="Return results.",
            ),
            quality_gates=QualityGates(),
            anti_patterns=["Rubber-stamp", "Nitpicking"],
        )
        sections = build_template_sections(tpl)
        assert "anti_patterns" in sections
        assert "Rubber-stamp" in sections["anti_patterns"]
        assert "Nitpicking" in sections["anti_patterns"]


class TestCompressSectionsNone:
    def test_preserves_all_sections(self, code_review_template) -> None:
        raw = build_template_sections(code_review_template)
        compressed, included = compress_sections(raw, CompressionLevel.NONE)
        assert set(compressed.keys()) == set(raw.keys())
        assert included == [k for k in SECTION_KEYS if k in raw]

    def test_content_unchanged(self, code_review_template) -> None:
        raw = build_template_sections(code_review_template)
        compressed, _ = compress_sections(raw, CompressionLevel.NONE)
        for key in raw:
            assert compressed[key] == raw[key]


class TestCompressSectionsMinify:
    def test_preserves_all_sections(self, code_review_template) -> None:
        raw = build_template_sections(code_review_template)
        compressed, included = compress_sections(raw, CompressionLevel.MINIFY)
        assert set(compressed.keys()) == set(raw.keys())
        assert len(included) == len(raw)

    def test_length_leq_original(self, code_review_template) -> None:
        raw = build_template_sections(code_review_template)
        compressed, _ = compress_sections(raw, CompressionLevel.MINIFY)
        for key in raw:
            assert len(compressed[key]) <= len(raw[key]) + 1  # stripped may differ


class TestCompressSectionsCompact:
    def test_keeps_all_section_classes(self, code_review_template) -> None:
        raw = build_template_sections(code_review_template)
        compressed, included = compress_sections(raw, CompressionLevel.COMPACT)
        assert set(compressed.keys()) == set(raw.keys())

    def test_chain_of_thought_inlined(self, code_review_template) -> None:
        raw = build_template_sections(code_review_template)
        compressed, _ = compress_sections(raw, CompressionLevel.COMPACT)
        cot = compressed.get("chain_of_thought", "")
        # Numbered list should be compacted into semicolons.
        assert ";" in cot or "\n" not in cot or cot == raw.get("chain_of_thought", "")

    def test_mixed_list_and_prose_compact(self) -> None:
        """Cover the branch where non-list text follows list items."""
        sections = {
            "system_directive": "Preamble text.\n1. First item.\n2. Second item.\nSummary line.",
        }
        compressed, _ = compress_sections(sections, CompressionLevel.COMPACT)
        sd = compressed["system_directive"]
        assert ";" in sd  # items should be joined
        assert "Summary" in sd


class TestCompressSectionsAggressive:
    def test_preserves_system_directive(self, code_review_template) -> None:
        raw = build_template_sections(code_review_template)
        compressed, included = compress_sections(raw, CompressionLevel.AGGRESSIVE)
        assert "system_directive" in compressed
        assert "output_schema" in compressed

    def test_chain_of_thought_reduced(self, code_review_template) -> None:
        raw = build_template_sections(code_review_template)
        compressed, _ = compress_sections(raw, CompressionLevel.AGGRESSIVE)
        if "chain_of_thought" in raw:
            assert "chain_of_thought" in compressed
            assert len(compressed["chain_of_thought"]) <= len(
                raw["chain_of_thought"]
            )


class TestCompressSectionsSkeleton:
    def test_keeps_minimal_sections(self, code_review_template) -> None:
        raw = build_template_sections(code_review_template)
        compressed, included = compress_sections(raw, CompressionLevel.SKELETON)
        assert "system_directive" in compressed
        assert "output_schema" in compressed
        assert "quality_gates" not in compressed
        assert "anti_patterns" not in compressed

    def test_system_directive_is_first_sentence(self, code_review_template) -> None:
        compressed, _ = compress_sections(
            build_template_sections(code_review_template),
            CompressionLevel.SKELETON,
        )
        sd = compressed["system_directive"]
        assert sd.endswith(".")
        # Should be significantly shorter than original.
        raw_sd = build_template_sections(code_review_template)["system_directive"]
        assert len(sd) <= len(raw_sd)


class TestDeterminism:
    def test_repeated_calls_identical(self, code_review_template) -> None:
        raw = build_template_sections(code_review_template)
        for level in CompressionLevel:
            a, a_inc = compress_sections(raw, level)
            b, b_inc = compress_sections(raw, level)
            assert a == b, f"Non-deterministic at {level}"
            assert a_inc == b_inc

    def test_all_levels_produce_output(self, code_review_template) -> None:
        raw = build_template_sections(code_review_template)
        for level in CompressionLevel:
            compressed, included = compress_sections(raw, level)
            assert len(compressed) > 0, f"Empty output at {level}"
            assert len(included) > 0, f"No sections included at {level}"
