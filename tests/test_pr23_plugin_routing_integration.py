"""PR-23 tests — plugin routing integration: preroute/postroute wiring."""

from __future__ import annotations

import textwrap
from pathlib import Path
from typing import Any

import pytest

from interceptor.config import Config, load_config
from interceptor.models.template import Template
from interceptor.routing.models import RouteMethod, RouteResult, RouteZone
from interceptor.routing.router import route
from interceptor.plugins.integration import build_plugin_runner, route_with_plugins
from interceptor.template_registry import TemplateRegistry


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


def _config() -> Config:
    return load_config()


def _registry() -> TemplateRegistry:
    return TemplateRegistry.load_all()


def _baseline_route(text: str) -> RouteResult:
    """Route with real config/registry, no plugins."""
    return route(text, _registry(), _config())


# ===================================================================
# A — No plugins directory → routing unchanged
# ===================================================================

class TestA_NoPluginsDir:
    """route_with_plugins without plugins dir matches route()."""

    def test_no_dir_unchanged(self, tmp_path: Path) -> None:
        nonexistent = tmp_path / "nope"
        result = route_with_plugins(
            "review my code", _registry(), _config(),
            plugins_dir=nonexistent,
        )
        baseline = _baseline_route("review my code")
        assert result.template_name == baseline.template_name
        assert result.zone == baseline.zone
        assert result.confidence == baseline.confidence


# ===================================================================
# B — Plugins dir exists but no valid runtime plugins
# ===================================================================

class TestB_EmptyPluginsDir:
    """Empty plugins directory → routing unchanged."""

    def test_empty_dir_unchanged(self, tmp_path: Path) -> None:
        plugins_dir = tmp_path / "plugins"
        plugins_dir.mkdir()
        result = route_with_plugins(
            "review my code", _registry(), _config(),
            plugins_dir=plugins_dir,
        )
        baseline = _baseline_route("review my code")
        assert result.template_name == baseline.template_name
        assert result.confidence == baseline.confidence


# ===================================================================
# C — Preroute hook modifies input used by real routing
# ===================================================================

class TestC_PrerouteModifiesInput:
    """Preroute plugin modifies text before routing sees it."""

    def test_preroute_effect(self, tmp_path: Path) -> None:
        plugins_dir = tmp_path / "plugins"
        _write_plugin(
            plugins_dir / "rerouter",
            "rerouter",
            '"preroute"',
            """\
            class Plugin:
                def preroute(self, text, ctx):
                    return "review this code carefully"
            """,
        )
        result = route_with_plugins(
            "explain something random", _registry(), _config(),
            plugins_dir=plugins_dir,
        )
        assert result.template_name == "code-review"


# ===================================================================
# D — Postroute hook modifies RouteResult
# ===================================================================

class TestD_PostrouteModifiesResult:
    """Postroute plugin can modify the RouteResult."""

    def test_postroute_effect(self, tmp_path: Path) -> None:
        plugins_dir = tmp_path / "plugins"
        _write_plugin(
            plugins_dir / "overrider",
            "overrider",
            '"postroute"',
            """\
            from interceptor.routing.models import RouteResult, RouteZone, RouteMethod

            class Plugin:
                def postroute(self, result, ctx):
                    return RouteResult(
                        template_name="architecture",
                        zone=RouteZone.AUTO_SELECT,
                        method=RouteMethod.SCORE_WINNER,
                        confidence=0.99,
                    )
            """,
        )
        result = route_with_plugins(
            "review my code", _registry(), _config(),
            plugins_dir=plugins_dir,
        )
        assert result.template_name == "architecture"
        assert result.confidence == 0.99


# ===================================================================
# E — Multiple preroute plugins in order
# ===================================================================

class TestE_MultiPrerouteOrder:
    """Multiple preroute plugins run in alphabetical discovery order."""

    def test_multi_preroute(self, tmp_path: Path) -> None:
        plugins_dir = tmp_path / "plugins"
        _write_plugin(
            plugins_dir / "aa-first",
            "aa-first",
            '"preroute"',
            """\
            class Plugin:
                def preroute(self, text, ctx):
                    return text + " >A"
            """,
        )
        _write_plugin(
            plugins_dir / "bb-second",
            "bb-second",
            '"preroute"',
            """\
            class Plugin:
                def preroute(self, text, ctx):
                    return text + " >B"
            """,
        )
        runner = build_plugin_runner(plugins_dir)
        out = runner.run_hook("preroute", "start")
        assert out == "start >A >B"


# ===================================================================
# F — Multiple postroute plugins in order
# ===================================================================

class TestF_MultiPostrouteOrder:
    """Multiple postroute plugins chain in order."""

    def test_multi_postroute(self, tmp_path: Path) -> None:
        plugins_dir = tmp_path / "plugins"
        _write_plugin(
            plugins_dir / "aa-first",
            "aa-first",
            '"postroute"',
            """\
            class Plugin:
                def postroute(self, result, ctx):
                    result.scores["aa"] = 1.0
                    return result
            """,
        )
        _write_plugin(
            plugins_dir / "bb-second",
            "bb-second",
            '"postroute"',
            """\
            class Plugin:
                def postroute(self, result, ctx):
                    result.scores["bb"] = 2.0
                    return result
            """,
        )
        result = route_with_plugins(
            "review my code", _registry(), _config(),
            plugins_dir=plugins_dir,
        )
        assert "aa" in result.scores
        assert "bb" in result.scores
        assert result.scores["aa"] == 1.0
        assert result.scores["bb"] == 2.0


# ===================================================================
# G — Preroute B sees A's output
# ===================================================================

class TestG_PrerouteChaining:
    """Plugin B receives the output of plugin A."""

    def test_chain_visibility(self, tmp_path: Path) -> None:
        plugins_dir = tmp_path / "plugins"
        _write_plugin(
            plugins_dir / "aa",
            "aa",
            '"preroute"',
            """\
            class Plugin:
                def preroute(self, text, ctx):
                    return text.upper()
            """,
        )
        _write_plugin(
            plugins_dir / "bb",
            "bb",
            '"preroute"',
            """\
            class Plugin:
                def preroute(self, text, ctx):
                    if text.isupper():
                        return text + " [SAW-UPPER]"
                    return text + " [NO-UPPER]"
            """,
        )
        runner = build_plugin_runner(plugins_dir)
        out = runner.run_hook("preroute", "hello")
        assert out == "HELLO [SAW-UPPER]"


# ===================================================================
# H — Postroute B sees A's output
# ===================================================================

class TestH_PostrouteChaining:
    """Postroute B receives A's modified RouteResult."""

    def test_post_chain(self, tmp_path: Path) -> None:
        plugins_dir = tmp_path / "plugins"
        _write_plugin(
            plugins_dir / "aa",
            "aa",
            '"postroute"',
            """\
            class Plugin:
                def postroute(self, result, ctx):
                    result.scores["marker-aa"] = 1.0
                    return result
            """,
        )
        _write_plugin(
            plugins_dir / "bb",
            "bb",
            '"postroute"',
            """\
            class Plugin:
                def postroute(self, result, ctx):
                    if "marker-aa" in result.scores:
                        result.scores["bb-saw-aa"] = 1.0
                    return result
            """,
        )
        result = route_with_plugins(
            "review my code", _registry(), _config(),
            plugins_dir=plugins_dir,
        )
        assert "marker-aa" in result.scores
        assert "bb-saw-aa" in result.scores


# ===================================================================
# I — Failing preroute → disabled, routing continues with original
# ===================================================================

class TestI_PreRouteCrash:
    """Crashing preroute plugin disabled; routing uses original input."""

    def test_preroute_crash_continues(self, tmp_path: Path) -> None:
        plugins_dir = tmp_path / "plugins"
        _write_plugin(
            plugins_dir / "crasher",
            "crasher",
            '"preroute"',
            """\
            class Plugin:
                def preroute(self, text, ctx):
                    raise RuntimeError("boom")
            """,
        )
        result = route_with_plugins(
            "review my code", _registry(), _config(),
            plugins_dir=plugins_dir,
        )
        baseline = _baseline_route("review my code")
        assert result.template_name == baseline.template_name


# ===================================================================
# J — Failing postroute → last good RouteResult preserved
# ===================================================================

class TestJ_PostRouteCrash:
    """Crashing postroute plugin disabled; RouteResult unchanged."""

    def test_postroute_crash_continues(self, tmp_path: Path) -> None:
        plugins_dir = tmp_path / "plugins"
        _write_plugin(
            plugins_dir / "crasher",
            "crasher",
            '"postroute"',
            """\
            class Plugin:
                def postroute(self, result, ctx):
                    raise ValueError("oops")
            """,
        )
        result = route_with_plugins(
            "review my code", _registry(), _config(),
            plugins_dir=plugins_dir,
        )
        baseline = _baseline_route("review my code")
        assert result.template_name == baseline.template_name
        assert result.confidence == baseline.confidence


# ===================================================================
# K — None from preroute → treated as failure
# ===================================================================

class TestK_PrerouteNone:
    """Preroute returning None → original input used for routing."""

    def test_none_preroute(self, tmp_path: Path) -> None:
        plugins_dir = tmp_path / "plugins"
        _write_plugin(
            plugins_dir / "noner",
            "noner",
            '"preroute"',
            """\
            class Plugin:
                def preroute(self, text, ctx):
                    return None
            """,
        )
        result = route_with_plugins(
            "review my code", _registry(), _config(),
            plugins_dir=plugins_dir,
        )
        baseline = _baseline_route("review my code")
        assert result.template_name == baseline.template_name


# ===================================================================
# L — None from postroute → treated as failure
# ===================================================================

class TestL_PostrouteNone:
    """Postroute returning None → RouteResult preserved."""

    def test_none_postroute(self, tmp_path: Path) -> None:
        plugins_dir = tmp_path / "plugins"
        _write_plugin(
            plugins_dir / "noner",
            "noner",
            '"postroute"',
            """\
            class Plugin:
                def postroute(self, result, ctx):
                    return None
            """,
        )
        result = route_with_plugins(
            "review my code", _registry(), _config(),
            plugins_dir=plugins_dir,
        )
        baseline = _baseline_route("review my code")
        assert result.template_name == baseline.template_name
        assert result.confidence == baseline.confidence


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
            '"preroute"',
            """\
            class Plugin:
                def preroute(self, text, ctx):
                    return text + " >A"
            """,
        )
        _write_plugin(
            plugins_dir / "bb-bad",
            "bb-bad",
            '"preroute"',
            """\
            class Plugin:
                def preroute(self, text, ctx):
                    raise RuntimeError("crash")
            """,
        )
        _write_plugin(
            plugins_dir / "cc-good",
            "cc-good",
            '"preroute"',
            """\
            class Plugin:
                def preroute(self, text, ctx):
                    return text + " >C"
            """,
        )
        runner = build_plugin_runner(plugins_dir)
        out = runner.run_hook("preroute", "start")
        assert out == "start >A >C"


# ===================================================================
# N — Next routing invocation starts fresh
# ===================================================================

class TestN_FreshInvocation:
    """Each route_with_plugins call creates a fresh runner."""

    def test_fresh_per_invocation(self, tmp_path: Path) -> None:
        plugins_dir = tmp_path / "plugins"
        _write_plugin(
            plugins_dir / "marker",
            "marker",
            '"postroute"',
            """\
            class Plugin:
                def postroute(self, result, ctx):
                    result.scores["plugin-marker"] = 1.0
                    return result
            """,
        )
        r1 = route_with_plugins(
            "review my code", _registry(), _config(),
            plugins_dir=plugins_dir,
        )
        r2 = route_with_plugins(
            "review my code", _registry(), _config(),
            plugins_dir=plugins_dir,
        )
        assert "plugin-marker" in r1.scores
        assert "plugin-marker" in r2.scores


# ===================================================================
# O — End-to-end proof via real routing function
# ===================================================================

class TestO_EndToEnd:
    """Real routing pipeline produces different output with plugin."""

    def test_real_end_to_end(self, tmp_path: Path) -> None:
        plugins_dir = tmp_path / "plugins"
        _write_plugin(
            plugins_dir / "force-arch",
            "force-arch",
            '"preroute", "postroute"',
            """\
            from interceptor.routing.models import RouteResult, RouteZone, RouteMethod

            class Plugin:
                def preroute(self, text, ctx):
                    return "design this system architecture"

                def postroute(self, result, ctx):
                    result.scores["plugin-touched"] = 1.0
                    return result
            """,
        )
        with_p = route_with_plugins(
            "review my code", _registry(), _config(),
            plugins_dir=plugins_dir,
        )

        empty = tmp_path / "empty"
        empty.mkdir()
        without_p = route_with_plugins(
            "review my code", _registry(), _config(),
            plugins_dir=empty,
        )

        assert with_p.template_name == "architecture"
        assert "plugin-touched" in with_p.scores
        assert without_p.template_name == "code-review"
        assert "plugin-touched" not in without_p.scores


# ===================================================================
# P — Regression: existing routing behavior unchanged
# ===================================================================

class TestP_Regression:
    """route_with_plugins with no plugins matches route() exactly."""

    def test_field_identical(self, tmp_path: Path) -> None:
        empty = tmp_path / "empty"
        empty.mkdir()
        text = "review this code for bugs and security"

        with_wrapper = route_with_plugins(
            text, _registry(), _config(), plugins_dir=empty,
        )
        baseline = route(text, _registry(), _config())

        assert with_wrapper.template_name == baseline.template_name
        assert with_wrapper.zone == baseline.zone
        assert with_wrapper.method == baseline.method
        assert with_wrapper.confidence == baseline.confidence
        assert with_wrapper.runner_up == baseline.runner_up


# ===================================================================
# Q — RouteResult type/field integrity after postroute
# ===================================================================

class TestQ_RouteResultIntegrity:
    """RouteResult preserves type and fields after postroute plugin use."""

    def test_type_preserved(self, tmp_path: Path) -> None:
        plugins_dir = tmp_path / "plugins"
        _write_plugin(
            plugins_dir / "modifier",
            "modifier",
            '"postroute"',
            """\
            class Plugin:
                def postroute(self, result, ctx):
                    result.scores["extra"] = 0.5
                    return result
            """,
        )
        result = route_with_plugins(
            "review my code", _registry(), _config(),
            plugins_dir=plugins_dir,
        )
        assert isinstance(result, RouteResult)
        assert isinstance(result.template_name, str)
        assert isinstance(result.zone, RouteZone)
        assert isinstance(result.method, RouteMethod)
        assert isinstance(result.confidence, float)
        assert "extra" in result.scores
