"""PR-22 tests — plugin compile integration: precompile/postcompile wiring."""

from __future__ import annotations

import textwrap
from pathlib import Path
from typing import Any

import pytest

from interceptor.compilation.assembler import compile_prompt
from interceptor.models.template import (
    Category,
    QualityGates,
    Template,
    TemplateMeta,
    TemplatePrompt,
    TemplateTriggers,
)
from interceptor.plugins.integration import build_plugin_runner, compile_with_plugins


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_VALID_TOML = """\
name = "{name}"
version = "1.0.0"
description = "Test plugin"
hooks = [{hooks}]
api_version = "v1"
min_compiler_version = "0.1.0"
max_compiler_version = "99.0.0"
"""


def _write_plugin(
    plugin_dir: Path,
    name: str,
    hooks: str,
    code: str,
) -> Path:
    """Write plugin.toml + plugin.py in one call."""
    plugin_dir.mkdir(parents=True, exist_ok=True)
    (plugin_dir / "plugin.toml").write_text(_VALID_TOML.format(name=name, hooks=hooks))
    (plugin_dir / "plugin.py").write_text(textwrap.dedent(code))
    return plugin_dir


def _minimal_template() -> Template:
    """A minimal valid Template for compilation tests."""
    return Template(
        meta=TemplateMeta(
            name="test-tpl",
            category=Category.EVALUATIVE,
            version="1.0.0",
            author="test",
        ),
        triggers=TemplateTriggers(en=["test"]),
        prompt=TemplatePrompt(
            system_directive="You are a test assistant.",
            chain_of_thought="Think step by step.",
            output_schema="Return plain text.",
        ),
        quality_gates=QualityGates(),
        anti_patterns=[],
    )


def _baseline_compile(raw_input: str = "hello world") -> str:
    """Compile with no plugins and return compiled_text."""
    tpl = _minimal_template()
    compiled, _ = compile_prompt(template=tpl, raw_input=raw_input)
    return compiled.compiled_text


# ===================================================================
# A — No plugins directory → unchanged compile
# ===================================================================

class TestA_NoPluginsDir:
    """compile_with_plugins without plugins dir matches compile_prompt."""

    def test_no_dir_unchanged(self, tmp_path: Path) -> None:
        nonexistent = tmp_path / "nope"
        tpl = _minimal_template()
        compiled, budget = compile_with_plugins(
            template=tpl, raw_input="hello world", plugins_dir=nonexistent,
        )
        baseline = _baseline_compile("hello world")
        assert compiled.compiled_text == baseline
        assert budget.fits


# ===================================================================
# B — Plugins dir exists but no valid runtime plugins
# ===================================================================

class TestB_EmptyPluginsDir:
    """Empty plugins directory → unchanged compile."""

    def test_empty_dir_unchanged(self, tmp_path: Path) -> None:
        plugins_dir = tmp_path / "plugins"
        plugins_dir.mkdir()
        tpl = _minimal_template()
        compiled, _ = compile_with_plugins(
            template=tpl, raw_input="hello world", plugins_dir=plugins_dir,
        )
        baseline = _baseline_compile("hello world")
        assert compiled.compiled_text == baseline


# ===================================================================
# C — Precompile hook modifies raw input before compilation
# ===================================================================

class TestC_PrecompileModifiesInput:
    """Precompile plugin modifies raw_input, affecting compiled output."""

    def test_precompile_effect(self, tmp_path: Path) -> None:
        plugins_dir = tmp_path / "plugins"
        _write_plugin(
            plugins_dir / "prefix",
            "prefix",
            '"precompile"',
            """\
            class Plugin:
                def precompile(self, text, ctx):
                    return "[PREFIXED] " + text
            """,
        )
        tpl = _minimal_template()
        compiled, _ = compile_with_plugins(
            template=tpl, raw_input="hello", plugins_dir=plugins_dir,
        )
        assert "[PREFIXED] hello" in compiled.compiled_text
        assert compiled.raw_input == "[PREFIXED] hello"


# ===================================================================
# D — Postcompile hook modifies final compiled string
# ===================================================================

class TestD_PostcompileModifiesOutput:
    """Postcompile plugin modifies the final compiled prompt string."""

    def test_postcompile_effect(self, tmp_path: Path) -> None:
        plugins_dir = tmp_path / "plugins"
        _write_plugin(
            plugins_dir / "suffix",
            "suffix",
            '"postcompile"',
            """\
            class Plugin:
                def postcompile(self, text, ctx):
                    return text + "\\n[PLUGIN-FOOTER]"
            """,
        )
        tpl = _minimal_template()
        compiled, _ = compile_with_plugins(
            template=tpl, raw_input="hello", plugins_dir=plugins_dir,
        )
        assert compiled.compiled_text.endswith("[PLUGIN-FOOTER]")


# ===================================================================
# E — Multiple precompile plugins in order
# ===================================================================

class TestE_MultiPrecompileOrder:
    """Multiple precompile plugins run in alphabetical discovery order."""

    def test_multi_precompile(self, tmp_path: Path) -> None:
        plugins_dir = tmp_path / "plugins"
        _write_plugin(
            plugins_dir / "aa-first",
            "aa-first",
            '"precompile"',
            """\
            class Plugin:
                def precompile(self, text, ctx):
                    return text + ">A"
            """,
        )
        _write_plugin(
            plugins_dir / "bb-second",
            "bb-second",
            '"precompile"',
            """\
            class Plugin:
                def precompile(self, text, ctx):
                    return text + ">B"
            """,
        )
        tpl = _minimal_template()
        compiled, _ = compile_with_plugins(
            template=tpl, raw_input="start", plugins_dir=plugins_dir,
        )
        assert "start>A>B" in compiled.compiled_text


# ===================================================================
# F — Multiple postcompile plugins in order
# ===================================================================

class TestF_MultiPostcompileOrder:
    """Multiple postcompile plugins chain in order."""

    def test_multi_postcompile(self, tmp_path: Path) -> None:
        plugins_dir = tmp_path / "plugins"
        _write_plugin(
            plugins_dir / "aa-first",
            "aa-first",
            '"postcompile"',
            """\
            class Plugin:
                def postcompile(self, text, ctx):
                    return text + " [post-A]"
            """,
        )
        _write_plugin(
            plugins_dir / "bb-second",
            "bb-second",
            '"postcompile"',
            """\
            class Plugin:
                def postcompile(self, text, ctx):
                    return text + " [post-B]"
            """,
        )
        tpl = _minimal_template()
        compiled, _ = compile_with_plugins(
            template=tpl, raw_input="hi", plugins_dir=plugins_dir,
        )
        assert compiled.compiled_text.endswith("[post-A] [post-B]")


# ===================================================================
# G — Precompile B sees A's output
# ===================================================================

class TestG_PrecompileChaining:
    """Plugin B receives the output of plugin A, not the original input."""

    def test_chain_visibility(self, tmp_path: Path) -> None:
        plugins_dir = tmp_path / "plugins"
        _write_plugin(
            plugins_dir / "aa",
            "aa",
            '"precompile"',
            """\
            class Plugin:
                def precompile(self, text, ctx):
                    return text.upper()
            """,
        )
        _write_plugin(
            plugins_dir / "bb",
            "bb",
            '"precompile"',
            """\
            class Plugin:
                def precompile(self, text, ctx):
                    return text + " [saw-upper]" if text.isupper() else text + " [no-upper]"
            """,
        )
        tpl = _minimal_template()
        compiled, _ = compile_with_plugins(
            template=tpl, raw_input="hello", plugins_dir=plugins_dir,
        )
        assert "HELLO [saw-upper]" in compiled.compiled_text


# ===================================================================
# H — Postcompile B sees A's output
# ===================================================================

class TestH_PostcompileChaining:
    """Postcompile B receives A's modified string."""

    def test_post_chain(self, tmp_path: Path) -> None:
        plugins_dir = tmp_path / "plugins"
        _write_plugin(
            plugins_dir / "aa",
            "aa",
            '"postcompile"',
            """\
            class Plugin:
                def postcompile(self, text, ctx):
                    return text + "<<AA>>"
            """,
        )
        _write_plugin(
            plugins_dir / "bb",
            "bb",
            '"postcompile"',
            """\
            class Plugin:
                def postcompile(self, text, ctx):
                    if "<<AA>>" in text:
                        return text + "<<BB-SAW-AA>>"
                    return text + "<<BB>>"
            """,
        )
        tpl = _minimal_template()
        compiled, _ = compile_with_plugins(
            template=tpl, raw_input="x", plugins_dir=plugins_dir,
        )
        assert "<<AA>><<BB-SAW-AA>>" in compiled.compiled_text


# ===================================================================
# I — Failing precompile → disabled, compile continues
# ===================================================================

class TestI_PrecompileCrash:
    """Crashing precompile plugin disabled; compilation uses original input."""

    def test_precompile_crash_continues(self, tmp_path: Path) -> None:
        plugins_dir = tmp_path / "plugins"
        _write_plugin(
            plugins_dir / "crasher",
            "crasher",
            '"precompile"',
            """\
            class Plugin:
                def precompile(self, text, ctx):
                    raise RuntimeError("boom")
            """,
        )
        tpl = _minimal_template()
        compiled, _ = compile_with_plugins(
            template=tpl, raw_input="safe", plugins_dir=plugins_dir,
        )
        baseline = _baseline_compile("safe")
        assert compiled.compiled_text == baseline


# ===================================================================
# J — Failing postcompile → disabled, last good string preserved
# ===================================================================

class TestJ_PostcompileCrash:
    """Crashing postcompile plugin disabled; compiled text unchanged."""

    def test_postcompile_crash_continues(self, tmp_path: Path) -> None:
        plugins_dir = tmp_path / "plugins"
        _write_plugin(
            plugins_dir / "crasher",
            "crasher",
            '"postcompile"',
            """\
            class Plugin:
                def postcompile(self, text, ctx):
                    raise ValueError("oops")
            """,
        )
        tpl = _minimal_template()
        compiled, _ = compile_with_plugins(
            template=tpl, raw_input="safe", plugins_dir=plugins_dir,
        )
        baseline = _baseline_compile("safe")
        assert compiled.compiled_text == baseline


# ===================================================================
# K — None from precompile → treated as failure
# ===================================================================

class TestK_PrecompileNone:
    """Precompile returning None → original input used."""

    def test_none_precompile(self, tmp_path: Path) -> None:
        plugins_dir = tmp_path / "plugins"
        _write_plugin(
            plugins_dir / "noner",
            "noner",
            '"precompile"',
            """\
            class Plugin:
                def precompile(self, text, ctx):
                    return None
            """,
        )
        tpl = _minimal_template()
        compiled, _ = compile_with_plugins(
            template=tpl, raw_input="safe", plugins_dir=plugins_dir,
        )
        baseline = _baseline_compile("safe")
        assert compiled.compiled_text == baseline


# ===================================================================
# L — None from postcompile → treated as failure
# ===================================================================

class TestL_PostcompileNone:
    """Postcompile returning None → compiled text preserved."""

    def test_none_postcompile(self, tmp_path: Path) -> None:
        plugins_dir = tmp_path / "plugins"
        _write_plugin(
            plugins_dir / "noner",
            "noner",
            '"postcompile"',
            """\
            class Plugin:
                def postcompile(self, text, ctx):
                    return None
            """,
        )
        tpl = _minimal_template()
        compiled, _ = compile_with_plugins(
            template=tpl, raw_input="safe", plugins_dir=plugins_dir,
        )
        baseline = _baseline_compile("safe")
        assert compiled.compiled_text == baseline


# ===================================================================
# M — One plugin failing doesn't disable healthy plugins
# ===================================================================

class TestM_HealthyPluginsSurvive:
    """Crashing plugin B doesn't disable plugins A or C."""

    def test_healthy_survive(self, tmp_path: Path) -> None:
        plugins_dir = tmp_path / "plugins"
        _write_plugin(
            plugins_dir / "aa-good",
            "aa-good",
            '"precompile"',
            """\
            class Plugin:
                def precompile(self, text, ctx):
                    return text + ">A"
            """,
        )
        _write_plugin(
            plugins_dir / "bb-bad",
            "bb-bad",
            '"precompile"',
            """\
            class Plugin:
                def precompile(self, text, ctx):
                    raise RuntimeError("crash")
            """,
        )
        _write_plugin(
            plugins_dir / "cc-good",
            "cc-good",
            '"precompile"',
            """\
            class Plugin:
                def precompile(self, text, ctx):
                    return text + ">C"
            """,
        )
        tpl = _minimal_template()
        compiled, _ = compile_with_plugins(
            template=tpl, raw_input="start", plugins_dir=plugins_dir,
        )
        # A runs, B crashes (value stays "start>A"), C gets "start>A"
        assert "start>A>C" in compiled.compiled_text


# ===================================================================
# N — Fresh invocation starts fresh
# ===================================================================

class TestN_FreshInvocation:
    """Each compile_with_plugins call creates a fresh runner."""

    def test_fresh_per_invocation(self, tmp_path: Path) -> None:
        plugins_dir = tmp_path / "plugins"
        _write_plugin(
            plugins_dir / "counter",
            "counter",
            '"precompile"',
            """\
            class Plugin:
                def precompile(self, text, ctx):
                    return text + " [pre]"
            """,
        )
        tpl = _minimal_template()

        c1, _ = compile_with_plugins(
            template=tpl, raw_input="first", plugins_dir=plugins_dir,
        )
        c2, _ = compile_with_plugins(
            template=tpl, raw_input="second", plugins_dir=plugins_dir,
        )
        assert "first [pre]" in c1.compiled_text
        assert "second [pre]" in c2.compiled_text


# ===================================================================
# O — End-to-end proof via real compile function
# ===================================================================

class TestO_EndToEnd:
    """Real compilation pipeline produces different output with plugin."""

    def test_real_end_to_end(self, tmp_path: Path) -> None:
        plugins_dir = tmp_path / "plugins"
        _write_plugin(
            plugins_dir / "marker",
            "marker",
            '"precompile", "postcompile"',
            """\
            class Plugin:
                def precompile(self, text, ctx):
                    return "[PLUGIN-PRE] " + text
                def postcompile(self, text, ctx):
                    return text + "\\n[PLUGIN-POST]"
            """,
        )
        tpl = _minimal_template()

        # With plugins
        with_p, _ = compile_with_plugins(
            template=tpl, raw_input="test input", plugins_dir=plugins_dir,
        )
        # Without plugins (empty dir)
        empty = tmp_path / "empty"
        empty.mkdir()
        without_p, _ = compile_with_plugins(
            template=tpl, raw_input="test input", plugins_dir=empty,
        )

        assert "[PLUGIN-PRE] test input" in with_p.compiled_text
        assert with_p.compiled_text.endswith("[PLUGIN-POST]")
        assert "[PLUGIN-PRE]" not in without_p.compiled_text
        assert "[PLUGIN-POST]" not in without_p.compiled_text


# ===================================================================
# P — Regression: existing compile behavior unchanged
# ===================================================================

class TestP_Regression:
    """compile_with_plugins with no plugins matches compile_prompt exactly."""

    def test_byte_identical(self, tmp_path: Path) -> None:
        empty = tmp_path / "empty"
        empty.mkdir()
        tpl = _minimal_template()
        raw = "regression test input with special chars: äöü ☺"

        with_wrapper, budget_w = compile_with_plugins(
            template=tpl, raw_input=raw, plugins_dir=empty,
        )
        baseline, budget_b = compile_prompt(template=tpl, raw_input=raw)

        assert with_wrapper.compiled_text == baseline.compiled_text
        assert with_wrapper.template_name == baseline.template_name
        assert with_wrapper.compression_level == baseline.compression_level
        assert with_wrapper.token_count_estimate == baseline.token_count_estimate
        assert budget_w.fits == budget_b.fits


# ===================================================================
# Q — build_plugin_runner utility
# ===================================================================

class TestQ_BuildPluginRunner:
    """build_plugin_runner handles edge cases gracefully."""

    def test_nonexistent_dir(self, tmp_path: Path) -> None:
        runner = build_plugin_runner(tmp_path / "nope")
        assert len(runner.active_plugins) == 0

    def test_empty_dir(self, tmp_path: Path) -> None:
        d = tmp_path / "empty"
        d.mkdir()
        runner = build_plugin_runner(d)
        assert len(runner.active_plugins) == 0

    def test_valid_plugin_loaded(self, tmp_path: Path) -> None:
        plugins_dir = tmp_path / "plugins"
        _write_plugin(
            plugins_dir / "good",
            "good",
            '"precompile"',
            """\
            class Plugin:
                def precompile(self, text, ctx):
                    return text
            """,
        )
        runner = build_plugin_runner(plugins_dir)
        assert len(runner.active_plugins) == 1

    def test_discovery_warnings_emitted(self, tmp_path: Path) -> None:
        plugins_dir = tmp_path / "plugins"
        plugins_dir.mkdir()
        bad_dir = plugins_dir / "bad-plugin"
        bad_dir.mkdir()
        (bad_dir / "plugin.toml").write_text("not valid toml {{{{")
        runner = build_plugin_runner(plugins_dir)
        assert len(runner.active_plugins) == 0

    def test_discovery_exception_returns_empty(self, tmp_path: Path, monkeypatch: Any) -> None:
        plugins_dir = tmp_path / "plugins"
        plugins_dir.mkdir()

        from interceptor.plugins import integration

        def _boom(*a: Any, **kw: Any) -> None:
            raise OSError("permission denied")

        monkeypatch.setattr(integration, "discover_plugins", _boom)
        runner = build_plugin_runner(plugins_dir)
        assert len(runner.active_plugins) == 0
